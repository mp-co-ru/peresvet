import json
on=json.load(open("/home/vovaman/work/projects/peresvet/src/configurator_grafana/Configurator.json"))["panels"][0]["options"]["onRender"]
a=on.find("saveChanges = () =>")
b=on.find("resetChanges =", a)
chunk=on[a:b]
i=chunk.find("prsFillTagLinkageUI")
print(chunk[i-300:i+1200] if i>=0 else "not found")
