#!/usr/bin/env python3
"""Patch Configurator.json onRender: deferred storage binding + tree hints for alerts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "src" / "configurator_grafana" / "Configurator.json"


def main():
    data = json.loads(CFG.read_text(encoding="utf-8"))
    on = data["panels"][0]["options"]["onRender"]

    old_bind = """function prsBindTagLinkageSelectorsOnce() {
  if (prsTagLinkageBound) return;
  prsTagLinkageBound = true;
  var selDs = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  var selCn = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedConnector");
  if (selDs) {
    selDs.addEventListener("change", function () {
      if (prsTagLinkageBusy) return;
      prsApplyTagStorageSelection();
    });
  }
"""

    new_bind = """function prsTagLinkageEffectiveStorageId(selDs) {
  if (!selDs) return "";
  if (selDs.classList.contains("value-changed")) {
    return (selDs.dataset.prsInitial || "").trim();
  }
  return (selDs.value || "").trim();
}

function prsBindTagLinkageSelectorsOnce() {
  if (prsTagLinkageBound) return;
  prsTagLinkageBound = true;
  var selDs = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  var selCn = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedConnector");
  if (selDs) {
    selDs.addEventListener("blur", function () {
      if (prsTagLinkageBusy) return;
      var init = selDs.getAttribute("init-value");
      if (init == null) init = selDs.dataset.prsInitial != null ? selDs.dataset.prsInitial : "";
      init = String(init).trim();
      var cur = (selDs.value || "").trim();
      if (init !== cur) selDs.classList.add("value-changed");
      else selDs.classList.remove("value-changed");
      if (typeof prsUpdateSaveResetButtons === "function") prsUpdateSaveResetButtons();
      var tid = ($("#div-nodeId").text() || "").trim();
      if (tid && typeof prsMaybeShowIntegrationalOpsForTagForm === "function") prsMaybeShowIntegrationalOpsForTagForm(tid);
    });
  }
"""

    if old_bind not in on:
        raise SystemExit("old_bind block not found")
    on = on.replace(old_bind, new_bind, 1)

    old_maybe = """function prsMaybeShowIntegrationalOpsForTagForm(tagId) {
  var selDs = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  if (!selDs || !selDs.value) {
    prsHideTagIntegrationalPanel();
    return;
  }
  var meta = prsTagLinkageDsMeta[selDs.value];
  var et = meta && meta.entityType;
  if (et === 2) {
    var fake = document.createElement("div");
    fake.setAttribute("data-ds-id", selDs.value);
"""

    new_maybe = """function prsMaybeShowIntegrationalOpsForTagForm(tagId) {
  var selDs = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  var dsId = typeof prsTagLinkageEffectiveStorageId === "function" ? prsTagLinkageEffectiveStorageId(selDs) : ((selDs && selDs.value) || "");
  if (!selDs || !dsId) {
    prsHideTagIntegrationalPanel();
    return;
  }
  var meta = prsTagLinkageDsMeta[dsId];
  var et = meta && meta.entityType;
  if (et === 2) {
    var fake = document.createElement("div");
    fake.setAttribute("data-ds-id", dsId);
"""

    if old_maybe not in on:
        raise SystemExit("prsMaybeShowIntegrationalOpsForTagForm block not found")
    on = on.replace(old_maybe, new_maybe, 1)

    # fake still has data-entity-id tagId — ok
    # Replace second selDs.value in that function if any left — check
    on = on.replace(
        'fake.setAttribute("data-ds-id", selDs.value);',
        'fake.setAttribute("data-ds-id", dsId);',
    )
    # May duplicate if already dsId - the new_maybe already sets dsId. The old string had selDs.value twice - we replaced first block. Need to fix remaining in same function - grep
    if 'fake.setAttribute("data-ds-id", selDs.value)' in on:
        on = on.replace('fake.setAttribute("data-ds-id", selDs.value)', 'fake.setAttribute("data-ds-id", dsId)', 1)

    old_integ_active = """function prsTagDataIntegrationalModeActive() {
  var sel = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  if (!sel || !sel.value) return false;
  var meta = prsTagLinkageDsMeta[sel.value];
  return !!(meta && meta.entityType === 2);
}"""

    new_integ_active = """function prsTagDataIntegrationalModeActive() {
  var sel = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  var id = typeof prsTagLinkageEffectiveStorageId === "function" ? prsTagLinkageEffectiveStorageId(sel) : ((sel && sel.value) || "");
  if (!id) return false;
  var meta = prsTagLinkageDsMeta[id];
  return !!(meta && meta.entityType === 2);
}"""

    if old_integ_active not in on:
        raise SystemExit("prsTagDataIntegrationalModeActive not found")
    on = on.replace(old_integ_active, new_integ_active, 1)

    old_refresh_read = """  var meta = sel && sel.value ? prsTagLinkageDsMeta[sel.value] : null;
  var et = meta && meta.entityType;"""

    new_refresh_read = """  var effId = sel && typeof prsTagLinkageEffectiveStorageId === "function" ? prsTagLinkageEffectiveStorageId(sel) : (sel && sel.value ? sel.value : "");
  var meta = effId ? prsTagLinkageDsMeta[effId] : null;
  var et = meta && meta.entityType;"""

    if old_refresh_read not in on:
        raise SystemExit("prsTagIntegRefreshReadPanel meta line not found")
    on = on.replace(old_refresh_read, new_refresh_read, 1)

    old_fetch = """function prsFetchAllDataStoragesWithTags(cb) {
  var url = window.location.protocol + "//" + window.location.hostname + "/v1/dataStorages/";
  var p = new URLSearchParams();
  p.append("base", "");
  p.append("getLinkedTags", "true");
  p.append("getLinkedAlerts", "false");
"""

    new_fetch = """function prsFetchAllDataStoragesWithTags(cb, opts) {
  opts = opts || {};
  var url = window.location.protocol + "//" + window.location.hostname + "/v1/dataStorages/";
  var p = new URLSearchParams();
  p.append("base", "");
  p.append("getLinkedTags", "true");
  p.append("getLinkedAlerts", opts.getLinkedAlerts ? "true" : "false");
"""

    if old_fetch not in on:
        raise SystemExit("prsFetchAllDataStoragesWithTags not found")
    on = on.replace(old_fetch, new_fetch, 1)

    old_hints = """function prsRefreshTagTreeHints() {
  prsFetchAllDataStoragesWithTags(function (_err, allDs) {
    var map = {};
    allDs.forEach(function (ds) {
      var cn = prsLdapAttrFirst(ds.attributes && ds.attributes.cn) || ds.id;
      (ds.linkedTags || []).forEach(function (lnk) {
        var tid = lnk.tagId || (lnk.attributes && prsLdapAttrFirst(lnk.attributes.cn));
        if (tid) map[String(tid)] = { id: ds.id, cn: cn };
      });
    });
    __prsConfiguratorHtmlNode.querySelectorAll('#tree .list-group-item[objectClass="prsTag"]').forEach(function (row) {
      if (row.id === "tags") return;
      row.classList.remove("prs-tag-tree-linked", "prs-tag-tree-unlinked");
      var info = map[row.id];
      if (info) {
        row.classList.add("prs-tag-tree-linked");
        row.setAttribute("title", "Хранилище данных: " + info.cn);
      } else {
        row.classList.add("prs-tag-tree-unlinked");
        row.setAttribute("title", "Нет привязки к хранилищу данных");
      }
    });
  });
}"""

    new_hints = """function prsRefreshTagTreeHints() {
  prsFetchAllDataStoragesWithTags(function (_err, allDs) {
    var map = {};
    allDs.forEach(function (ds) {
      var cn = prsLdapAttrFirst(ds.attributes && ds.attributes.cn) || ds.id;
      (ds.linkedTags || []).forEach(function (lnk) {
        var tid = lnk.tagId || (lnk.attributes && prsLdapAttrFirst(lnk.attributes.cn));
        if (tid) map[String(tid)] = { id: ds.id, cn: cn };
      });
      (ds.linkedAlerts || []).forEach(function (lnk) {
        var aid = lnk.alertId || (lnk.attributes && prsLdapAttrFirst(lnk.attributes.cn));
        if (aid) map[String(aid)] = { id: ds.id, cn: cn };
      });
    });
    __prsConfiguratorHtmlNode.querySelectorAll('#tree .list-group-item[objectClass="prsTag"], #tree .list-group-item[objectClass="prsAlert"]').forEach(function (row) {
      if (row.id === "tags") return;
      row.classList.remove("prs-tag-tree-linked", "prs-tag-tree-unlinked");
      var info = map[row.id];
      if (info) {
        row.classList.add("prs-tag-tree-linked");
        row.setAttribute("title", "Хранилище данных: " + info.cn);
      } else {
        row.classList.add("prs-tag-tree-unlinked");
        row.setAttribute("title", "Нет привязки к хранилищу данных");
      }
    });
  }, { getLinkedAlerts: true });
}"""

    if old_hints not in on:
        raise SystemExit("prsRefreshTagTreeHints not found")
    on = on.replace(old_hints, new_hints, 1)

    old_apply = """function prsApplyTagStorageSelection() {
  var tagId = ($("#div-nodeId").text() || "").trim();
  var sel = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
  if (!sel || !tagId) return;
  var prev = (sel.dataset.prsInitial || "").trim();
  var next = (sel.value || "").trim();
  if (prev === next) {
    prsMaybeShowIntegrationalOpsForTagForm(tagId);
    prsFetchAllDataStoragesWithTags(function (_e, ds2) { prsUpdateTagLinkedStoreDetail(tagId, ds2); });
    return;
  }
  prsTagLinkageBusy = true;
  var urlBase = window.location.protocol + "//" + window.location.hostname + "/v1/dataStorages/";
  function put(body) {
    return fetch(urlBase, {
      method: "PUT",
      body: JSON.stringify(body),
      headers: new Headers({ "Content-Type": "application/json" })
    });
  }
  function done(ok) {
    prsTagLinkageBusy = false;
    if (ok) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", "Привязка к хранилищу обновлена.", true);
      sel.dataset.prsInitial = next;
      prsRefreshTagTreeHints();
      prsRefreshDataStorages();
    } else {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка привязки к хранилищу (ожидался 202).", false);
      prsFillTagLinkageUI(tagId);
    }
    prsMaybeShowIntegrationalOpsForTagForm(tagId);
    prsFetchAllDataStoragesWithTags(function (_e, ds2) { prsUpdateTagLinkedStoreDetail(tagId, ds2); });
  }
  if (prev) {
    put({ id: prev, unlinkTags: [tagId] }).then(function (r1) {
      if (r1.status !== 202) { done(false); return; }
      if (!next) { done(true); return; }
      put({ id: next, linkedTags: [{ tagId: tagId }] }).then(function (r2) {
        done(r2.status === 202);
      }).catch(function () { done(false); });
    }).catch(function () { done(false); });
  } else if (next) {
    put({ id: next, linkedTags: [{ tagId: tagId }] }).then(function (r) {
      done(r.status === 202);
    }).catch(function () { done(false); });
  } else {
    prsTagLinkageBusy = false;
  }
}
"""

    new_apply = """function prsSaveTagStorageBindingPromise() {
  return new Promise(function (resolve) {
    var tagId = ($("#div-nodeId").text() || "").trim();
    var sel = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
    if (!sel || !tagId) {
      resolve(true);
      return;
    }
    var prev = (sel.dataset.prsInitial || "").trim();
    var next = (sel.value || "").trim();
    if (prev === next) {
      prsMaybeShowIntegrationalOpsForTagForm(tagId);
      prsFetchAllDataStoragesWithTags(function (_e, ds2) { prsUpdateTagLinkedStoreDetail(tagId, ds2); });
      resolve(true);
      return;
    }
    prsTagLinkageBusy = true;
    var urlBase = window.location.protocol + "//" + window.location.hostname + "/v1/dataStorages/";
    function put(body) {
      return fetch(urlBase, {
        method: "PUT",
        body: JSON.stringify(body),
        headers: new Headers({ "Content-Type": "application/json" })
      });
    }
    function done(ok) {
      prsTagLinkageBusy = false;
      if (ok) {
        showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", "Привязка к хранилищу обновлена.", true);
        sel.dataset.prsInitial = next;
        prsRefreshTagTreeHints();
        prsRefreshDataStorages();
      } else {
        showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка привязки к хранилищу (ожидался 202).", false);
        prsFillTagLinkageUI(tagId);
      }
      prsMaybeShowIntegrationalOpsForTagForm(tagId);
      prsFetchAllDataStoragesWithTags(function (_e, ds2) { prsUpdateTagLinkedStoreDetail(tagId, ds2); });
      resolve(ok);
    }
    if (prev) {
      put({ id: prev, unlinkTags: [tagId] }).then(function (r1) {
        if (r1.status !== 202) { done(false); return; }
        if (!next) { done(true); return; }
        put({ id: next, linkedTags: [{ tagId: tagId }] }).then(function (r2) {
          done(r2.status === 202);
        }).catch(function () { done(false); });
      }).catch(function () { done(false); });
    } else if (next) {
      put({ id: next, linkedTags: [{ tagId: tagId }] }).then(function (r) {
        done(r.status === 202);
      }).catch(function () { done(false); });
    } else {
      prsTagLinkageBusy = false;
      resolve(true);
    }
  });
}
"""

    if old_apply not in on:
        raise SystemExit("prsApplyTagStorageSelection not found")
    on = on.replace(old_apply, new_apply, 1)

    old_fill_busy = """      prsTagLinkageBusy = true;
      if (selDs) selDs.dataset.prsInitial = selDs.value;
      if (selCn) selCn.dataset.prsInitial = selCn.value;
      prsTagLinkageBusy = false;
"""

    new_fill_busy = """      prsTagLinkageBusy = true;
      if (selDs) {
        selDs.dataset.prsInitial = selDs.value;
        selDs.setAttribute("init-value", selDs.value);
        selDs.classList.remove("value-changed");
      }
      if (selCn) selCn.dataset.prsInitial = selCn.value;
      prsTagLinkageBusy = false;
"""

    if old_fill_busy not in on:
        raise SystemExit("prsFillTagLinkageUI busy block not found")
    on = on.replace(old_fill_busy, new_fill_busy, 1)

    # saveChanges: replace early prsTag returns with chained version
    old_early = """  var prsConnTagBindDirty = !!__prsConfiguratorHtmlNode.querySelector(".prs-conn-tag-binding.value-changed");
  var hasTagAttrChanges = cnChanged || Object.keys(payload.attributes).length > 0;
  if (objectClass === "prsTag" && !hasTagAttrChanges && prsConnTagBindDirty) {
    prsSaveConnectorTagBindingAttrsPromise().then(function (ok) {
      if (ok) {
        var nid = $("#div-nodeId").text();
        prsFillTagLinkageUI(nid);
        prsUpdateSaveResetButtons();
        changeTagDataPanelOnSave();
      }
    });
    return;
  }
  if (objectClass === "prsTag" && !hasTagAttrChanges && !prsConnTagBindDirty && typeof prsLinkedTagOpsDirtyFlag !== "undefined" && prsLinkedTagOpsDirtyFlag) {
    prsSaveLinkedTagV2Promise().then(function (okL) {
      if (okL) prsLinkedTagOpsDirtyFlag = false;
      prsUpdateSaveResetButtons();
      changeTagDataPanelOnSave();
    });
    return;
  }
"""

    new_early = """  var prsConnTagBindDirty = !!__prsConfiguratorHtmlNode.querySelector(".prs-conn-tag-binding.value-changed");
  var prsTagStorageBindDirty = !!(function () {
    var s = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
    return s && s.classList.contains("value-changed");
  })();
  var hasTagAttrChanges = cnChanged || Object.keys(payload.attributes).length > 0;
  if (objectClass === "prsTag" && !hasTagAttrChanges) {
    var stD = prsTagStorageBindDirty;
    var cnD = prsConnTagBindDirty;
    var lkD = typeof prsLinkedTagOpsDirtyFlag !== "undefined" && prsLinkedTagOpsDirtyFlag;
    if (stD || cnD || lkD) {
      var nid0 = $("#div-nodeId").text();
      function afterAll() {
        prsFillTagLinkageUI(nid0);
        prsUpdateSaveResetButtons();
        changeTagDataPanelOnSave();
      }
      function doLinked() {
        if (!lkD) {
          afterAll();
          return;
        }
        prsSaveLinkedTagV2Promise().then(function (okL) {
          if (okL) prsLinkedTagOpsDirtyFlag = false;
          afterAll();
        });
      }
      function doConn() {
        if (!cnD) {
          doLinked();
          return;
        }
        prsSaveConnectorTagBindingAttrsPromise().then(function (ok2) {
          if (!ok2) return;
          doLinked();
        });
      }
      function doStorage() {
        if (!stD) {
          doConn();
          return;
        }
        prsSaveTagStorageBindingPromise().then(function (okS) {
          if (!okS) return;
          var ss = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
          if (ss) {
            ss.setAttribute("init-value", ss.value);
            ss.classList.remove("value-changed");
          }
          doConn();
        });
      }
      doStorage();
      return;
    }
  }
"""

    if old_early not in on:
        raise SystemExit("saveChanges early prsTag block not found")
    on = on.replace(old_early, new_early, 1)

    old_success = """    changedElements.map((element) => {
      if (element.classList.contains("prs-conn-tag-binding")) return;
      element.setAttribute("init-value", element.value);
      element.classList.remove("value-changed");
    });
    if (objectClass === "prsMethod") {
      prsMethodInitiatorInit = JSON.stringify([...prsMethodInitiatorIds].map(String).sort());
    }
    prsUpdateSaveResetButtons();

    if (objectClass === "prsTag" && prsConnTagBindDirty) {
      prsSaveConnectorTagBindingAttrsPromise().then(function (ok2) {
        if (ok2) {
          prsFillTagLinkageUI(nodeId);
        }
        if (typeof prsLinkedTagOpsDirtyFlag !== "undefined" && prsLinkedTagOpsDirtyFlag) {
          prsSaveLinkedTagV2Promise().then(function (ok3) {
            if (ok3) prsLinkedTagOpsDirtyFlag = false;
            prsUpdateSaveResetButtons();
            changeTagDataPanelOnSave();
          });
        } else {
          prsUpdateSaveResetButtons();
          changeTagDataPanelOnSave();
        }
      });
    } else if (objectClass === "prsTag" && typeof prsLinkedTagOpsDirtyFlag !== "undefined" && prsLinkedTagOpsDirtyFlag) {
      prsSaveLinkedTagV2Promise().then(function (ok3) {
        if (ok3) prsLinkedTagOpsDirtyFlag = false;
        prsUpdateSaveResetButtons();
        changeTagDataPanelOnSave();
      });
    } else {
      changeTagDataPanelOnSave();
    }
"""

    new_success = """    var storageWasDirty = !!(function () {
      var s = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
      return s && s.classList.contains("value-changed");
    })();
    changedElements.map((element) => {
      if (element.classList.contains("prs-conn-tag-binding")) return;
      if (element.id === "select-prsTagLinkedStorage") return;
      element.setAttribute("init-value", element.value);
      element.classList.remove("value-changed");
    });
    if (objectClass === "prsMethod") {
      prsMethodInitiatorInit = JSON.stringify([...prsMethodInitiatorIds].map(String).sort());
    }
    prsUpdateSaveResetButtons();

    if (objectClass === "prsTag") {
      function finishTagSideSaves() {
        prsUpdateSaveResetButtons();
        changeTagDataPanelOnSave();
      }
      function chainLinked3() {
        if (!(typeof prsLinkedTagOpsDirtyFlag !== "undefined" && prsLinkedTagOpsDirtyFlag)) {
          finishTagSideSaves();
          return;
        }
        prsSaveLinkedTagV2Promise().then(function (ok3) {
          if (ok3) prsLinkedTagOpsDirtyFlag = false;
          finishTagSideSaves();
        });
      }
      function chainConn3() {
        if (!prsConnTagBindDirty) {
          chainLinked3();
          return;
        }
        prsSaveConnectorTagBindingAttrsPromise().then(function (ok2) {
          if (ok2) prsFillTagLinkageUI(nodeId);
          chainLinked3();
        });
      }
      function chainStorage3() {
        if (!storageWasDirty) {
          chainConn3();
          return;
        }
        prsSaveTagStorageBindingPromise().then(function (okS) {
          if (okS) {
            var ss = __prsConfiguratorHtmlNode.getElementById("select-prsTagLinkedStorage");
            if (ss) {
              ss.setAttribute("init-value", ss.value);
              ss.classList.remove("value-changed");
            }
          }
          chainConn3();
        });
      }
      chainStorage3();
    } else {
      changeTagDataPanelOnSave();
    }
"""

    if old_success not in on:
        raise SystemExit("saveChanges success block not found")
    on = on.replace(old_success, new_success, 1)

    data["panels"][0]["options"]["onRender"] = on

    css = data["panels"][0]["options"]["css"]
    css_inject = """
/* Непривязанные к хранилищу теги/тревоги — точка у подписи */
#tree .list-group-item.prsTag.prs-tag-tree-unlinked .prs-tree-label::after,
#tree .list-group-item.prsAlert.prs-tag-tree-unlinked .prs-tree-label::after {
  content: "";
  display: inline-block;
  width: 0.45rem;
  height: 0.45rem;
  margin-left: 0.35rem;
  border-radius: 50%;
  background: var(--ioterra-rust, #a34a28);
  box-shadow: 0 0 0 1px rgba(163, 74, 40, 0.35);
  vertical-align: 0.12em;
}
#tree .list-group-item.prsAlert.prs-tag-tree-linked > .item-icon {
  color: var(--ioterra-teal, #2c707f) !important;
}
#tree .list-group-item.prsAlert.prs-tag-tree-unlinked > .item-icon {
  color: var(--ioterra-rust, #a34a28) !important;
}
"""
    marker = "/* Панель v2 привязки — под полями формы */"
    if css_inject.strip() not in css:
        if marker not in css:
            raise SystemExit("CSS marker not found")
        css = css.replace(marker, css_inject.strip() + "\n" + marker, 1)
    data["panels"][0]["options"]["css"] = css

    CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK:", CFG)


if __name__ == "__main__":
    main()
