// Раздача одного H.264 всем зрителям WebRTC.
//
// Картинку кодирует ffmpeg в подхвате. Этот процесс только режет уже
// готовые кадры в RTP и отдаёт копию каждому PeerConnection.
// Все зрители делят один UDP-порт и один TCP-порт.
package main

import (
	"bufio"
	"encoding/binary"
	"encoding/json"
	"flag"
	"io"
	"log"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/pion/ice/v4"
	"github.com/pion/webrtc/v4"
	"github.com/pion/webrtc/v4/pkg/media"
)

const frameDuration = time.Second / 15

func main() {
	port := flag.Int("port", 8189, "UDP и TCP порт ICE")
	httpAddr := flag.String("http", "127.0.0.1:8190", "адрес сигналинга")
	ingestAddr := flag.String("ingest", "127.0.0.1:8191", "адрес приёма кадров")
	flag.Parse()

	udpMux, err := ice.NewMultiUDPMuxFromPort(*port)
	if err != nil {
		log.Fatalf("udp: %v", err)
	}
	tcpListener, err := net.ListenTCP("tcp", &net.TCPAddr{IP: net.IPv4zero, Port: *port})
	if err != nil {
		log.Fatalf("tcp: %v", err)
	}
	setting := webrtc.SettingEngine{}
	setting.SetICEUDPMux(udpMux)
	setting.SetICETCPMux(webrtc.NewICETCPMux(nil, tcpListener, 8))
	setting.SetNetworkTypes([]webrtc.NetworkType{
		webrtc.NetworkTypeUDP4,
		webrtc.NetworkTypeTCP4,
	})
	api := webrtc.NewAPI(webrtc.WithSettingEngine(setting))
	hub := newHub()

	go serveIngest(*ingestAddr, hub)

	mux := http.NewServeMux()
	mux.HandleFunc("/offer", func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPost {
			http.Error(writer, "нужен POST", http.StatusMethodNotAllowed)
			return
		}
		var body offerRequest
		if err := json.NewDecoder(io.LimitReader(request.Body, 1<<20)).Decode(&body); err != nil {
			http.Error(writer, "не удалось прочитать offer", http.StatusBadRequest)
			return
		}
		answer, err := hub.answer(api, body)
		if err != nil {
			log.Printf("offer %s: %v", body.ConnectorID, err)
			http.Error(writer, err.Error(), http.StatusBadRequest)
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(writer).Encode(answer)
	})
	log.Printf("WebRTC: ICE %d, сигналинг %s, кадры %s", *port, *httpAddr, *ingestAddr)
	log.Fatal(http.ListenAndServe(*httpAddr, mux))
}

type offerRequest struct {
	ConnectorID string `json:"connectorId"`
	SDP         string `json:"sdp"`
	Type        string `json:"type"`
}

type hub struct {
	mu        sync.Mutex
	tracks    map[string]*webrtc.TrackLocalStaticSample
	peers     map[*webrtc.PeerConnection]struct{}
	keyframes map[string][]byte
}

func newHub() *hub {
	return &hub{
		tracks:    map[string]*webrtc.TrackLocalStaticSample{},
		peers:     map[*webrtc.PeerConnection]struct{}{},
		keyframes: map[string][]byte{},
	}
}

func (h *hub) track(id string) (*webrtc.TrackLocalStaticSample, error) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if track, ok := h.tracks[id]; ok {
		return track, nil
	}
	track, err := webrtc.NewTrackLocalStaticSample(
		webrtc.RTPCodecCapability{
			MimeType:    webrtc.MimeTypeH264,
			SDPFmtpLine: "level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f",
			ClockRate:   90000,
		},
		"video",
		"peresvet",
	)
	if err != nil {
		return nil, err
	}
	h.tracks[id] = track
	return track, nil
}

func (h *hub) answer(api *webrtc.API, body offerRequest) (*webrtc.SessionDescription, error) {
	if body.ConnectorID == "" || body.SDP == "" {
		return nil, errString("нужны connectorId и sdp")
	}
	track, err := h.track(body.ConnectorID)
	if err != nil {
		return nil, err
	}
	peer, err := api.NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		return nil, err
	}
	if _, err = peer.AddTrack(track); err != nil {
		_ = peer.Close()
		return nil, err
	}
	h.mu.Lock()
	h.peers[peer] = struct{}{}
	h.mu.Unlock()
	peer.OnConnectionStateChange(func(state webrtc.PeerConnectionState) {
		log.Printf("зритель %s: %s", body.ConnectorID, state.String())
		if state == webrtc.PeerConnectionStateConnected {
			h.sendKeyframe(body.ConnectorID)
			return
		}
		// Disconnected ещё может вернуться в connected. Закрываем только отказ.
		if state == webrtc.PeerConnectionStateFailed ||
			state == webrtc.PeerConnectionStateClosed {
			_ = peer.Close()
			h.mu.Lock()
			delete(h.peers, peer)
			h.mu.Unlock()
		}
	})
	if err = peer.SetRemoteDescription(webrtc.SessionDescription{
		Type: webrtc.SDPTypeOffer,
		SDP:  body.SDP,
	}); err != nil {
		_ = peer.Close()
		return nil, err
	}
	answer, err := peer.CreateAnswer(nil)
	if err != nil {
		_ = peer.Close()
		return nil, err
	}
	gatherDone := webrtc.GatheringCompletePromise(peer)
	if err = peer.SetLocalDescription(answer); err != nil {
		_ = peer.Close()
		return nil, err
	}
	<-gatherDone
	local := peer.LocalDescription()
	if local == nil {
		_ = peer.Close()
		return nil, errString("нет локального SDP")
	}
	return local, nil
}

func (h *hub) write(id string, frame []byte) {
	if isKeyframe(frame) {
		h.mu.Lock()
		h.keyframes[id] = append([]byte(nil), frame...)
		h.mu.Unlock()
	}
	track, err := h.track(id)
	if err != nil {
		log.Printf("кадр %s: %v", id, err)
		return
	}
	if err = track.WriteSample(media.Sample{Data: frame, Duration: frameDuration}); err != nil {
		log.Printf("кадр %s: %v", id, err)
	}
}

func (h *hub) sendKeyframe(id string) {
	h.mu.Lock()
	frame := append([]byte(nil), h.keyframes[id]...)
	h.mu.Unlock()
	if len(frame) == 0 {
		return
	}
	h.write(id, frame)
}

func isKeyframe(frame []byte) bool {
	offset := 0
	for offset < len(frame) {
		rel := bytesIndex(frame[offset:])
		if rel < 0 {
			return false
		}
		nal := offset + rel + 3
		if nal < len(frame) && frame[nal]&0x1f == 5 {
			return true
		}
		offset = nal
	}
	return false
}

func bytesIndex(frame []byte) int {
	for i := 0; i+2 < len(frame); i++ {
		if frame[i] == 0 && frame[i+1] == 0 && frame[i+2] == 1 {
			return i
		}
	}
	return -1
}

func serveIngest(addr string, h *hub) {
	listener, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatalf("кадры: %v", err)
	}
	for {
		conn, err := listener.Accept()
		if err != nil {
			log.Printf("кадры: %v", err)
			continue
		}
		go readIngest(conn, h)
	}
}

func readIngest(conn net.Conn, h *hub) {
	defer conn.Close()
	reader := bufio.NewReader(conn)
	line, err := reader.ReadString('\n')
	if err != nil {
		return
	}
	id := strings.TrimSpace(line)
	if id == "" {
		return
	}
	log.Printf("камера %s: поток кадров", id)
	for {
		var size uint32
		if err = binary.Read(reader, binary.BigEndian, &size); err != nil {
			return
		}
		if size == 0 || size > 2*1024*1024 {
			return
		}
		frame := make([]byte, size)
		if _, err = io.ReadFull(reader, frame); err != nil {
			return
		}
		h.write(id, frame)
	}
}

type errString string

func (e errString) Error() string { return string(e) }
