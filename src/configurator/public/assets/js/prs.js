var pluginName = "bstreeview",
  defaults = {
    expandIcon: 'fa fa-angle-down fa-fw',
    collapseIcon: 'fa fa-angle-right fa-fw',
    expandClass: 'show',
    indent: 1.25,
    parentsMarginLeft: '1.25rem',
    openNodeLinkOnNewTab: true

  };
/**
 * bstreeview HTML templates.
 */
var templates = {
  treeview: '<div class="bstreeview"></div>',
  treeviewItem: '<div role="treeitem" class="list-group-item" data-bs-toggle="collapse"></div>',
  treeviewGroupItem: '<div role="group" class="list-group collapse" id="itemid"></div>',
  treeviewItemStateIcon: '<i class="state-icon"></i>',
  treeviewItemIcon: '<i class="item-icon"></i>'
};
/**
 * BsTreeview Plugin constructor.
 * @param {*} element
 * @param {*} options
 */
function bstreeView(element, options) {
  this.element = element;
  this.itemIdPrefix = element.id + "-item-";
  this.settings = $.extend({}, defaults, options);
  this.init();
}
/**
 * Avoid plugin conflict.
 */
$.extend(bstreeView.prototype, {
  /**
   * bstreeview intialize.
   */
  init: function () {
    this.tree = [];
    this.nodes = [];
    // Retrieve bstreeview Json Data.
    if (this.settings.data) {
      if (this.settings.data.isPrototypeOf(String)) {
        this.settings.data = $.parseJSON(this.settings.data);
      }
      this.tree = $.extend(true, [], this.settings.data);
      delete this.settings.data;
    }
    // Set main bstreeview class to element.
    $(this.element).addClass('bstreeview');

    this.initData({ nodes: this.tree });
    var _this = this;
    this.build($(this.element), this.tree, 0);
    // Update angle icon on collapse
    $(this.element).on('click', '.list-group-item', function (e) {
      $('.state-icon', this)
        .toggleClass(_this.settings.expandIcon)
        .toggleClass(_this.settings.collapseIcon);
      // navigate to href if present
      if (e.target.hasAttribute('href')) {
        if (_this.settings.openNodeLinkOnNewTab) {
          window.open(e.target.getAttribute('href'), '_blank');
        }
        else {
          window.location = e.target.getAttribute('href');
        }
      }
      else {
        // Toggle the data-bs-target. Issue with Bootstrap toggle and dynamic code
        $($(this).attr("data-bs-target")).collapse('toggle');
      }
    });
  },
  /**
   * Initialize treeview Data.
   * @param {*} node
   */
  initData: function (node) {
    if (!node.nodes) return;
    var parent = node;
    var _this = this;
    $.each(node.nodes, function checkStates(index, node) {

      node.nodeId = _this.nodes.length;
      node.parentId = parent.nodeId;
      _this.nodes.push(node);

      if (node.nodes) {
        _this.initData(node);
      }
    });
  },
  /**
   * Build treeview.
   * @param {*} parentElement
   * @param {*} nodes
   * @param {*} depth
   */
  build: function (parentElement, nodes, depth) {
    var _this = this;
    // Calculate item padding.
    var leftPadding = _this.settings.parentsMarginLeft;
    //var leftPadding = 0;

    if (depth > 1) {
      leftPadding = (_this.settings.parentsMarginLeft + depth * _this.settings.indent).toString() + "rem;";
    }
    depth += 1;
    // Add each node and sub-nodes.
    $.each(nodes, function addNodes(id, node) {
      // Main node element.
      var treeItem = $(templates.treeviewItem)
        .attr('data-bs-target', "#" + _this.itemIdPrefix + node.nodeId)
        .attr('style', 'padding-left:' + leftPadding)
        .attr('aria-level', depth);
      // Set Expand and Collapse icones.
      if (node.nodes) {
        var treeItemStateIcon = $(templates.treeviewItemStateIcon)
          .addClass((node.expanded) ? _this.settings.expandIcon : _this.settings.collapseIcon);
        treeItem.append(treeItemStateIcon);
      }
      // set node icon if exist.
      if (node.icon) {
        var treeItemIcon = $(templates.treeviewItemIcon)
          .addClass(node.icon);
        treeItem.append(treeItemIcon);
      }

      Object.entries(node).map((entry) => {
        switch (entry[0]) {
          case "text":
            treeItem.append(node.text);
            break;
          case "class":
            treeItem.addClass(node.class);
            break;
          case "nodes":
          case "nodeId":
          case "parentId":
          case "icon":
            break;
          default:
            treeItem.attr(entry[0], entry[1]);
            break;
        }
      });

      // Attach node to parent.
      parentElement.append(treeItem);
      // Build child nodes.
      if (node.nodes) {
        // Node group item.
        var treeGroup = $(templates.treeviewGroupItem)
          .attr('id', _this.itemIdPrefix + node.nodeId);
        parentElement.append(treeGroup);
        _this.build(treeGroup, node.nodes, depth);
        if (node.expanded) {
          treeGroup.addClass(_this.settings.expandClass);
        }
      }
    });
  }
});

// A really lightweight plugin wrapper around the constructor,
// preventing against multiple instantiations
$.fn[pluginName] = function (options) {
  return this.each(function () {
    if (!$.data(this, "plugin_" + pluginName)) {
      $.data(this, "plugin_" +
        pluginName, new bstreeView(this, options));
    }
  });
};


// начало ------------------------------------------------------------------------------------------------------------------------

initiatorsTabClicked = (butName) => {
  if (butName === "schedules") {
    $("#v-pills-Tags-tab").removeClass("active");
    $("#v-pills-Tags-tab").attr("aria-selected", "false");

    $("#v-pills-Schedules-tab").addClass("active");
    $("#v-pills-Schedules-tab").attr("aria-selected", "true");

    $("#v-pills-Tags").removeClass("show active");
    $("#v-pills-Schedules").addClass("show active");
  } else {
    $("#v-pills-Tags-tab").addClass("active");
    $("#v-pills-Tags-tab").attr("aria-selected", "true");

    $("#v-pills-Schedules-tab").removeClass("active");
    $("#v-pills-Schedules-tab").attr("aria-selected", "false");

    $("#v-pills-Tags").addClass("show active");
    $("#v-pills-Schedules").removeClass("show active");
  }
}


var topNodes = [
  {
    id: "objects",
    text: "Объекты",
    icon: "fa-solid fa-object-group",
    objectClass: "prsObject",
    tabindex: "0",
    onclick: "clickNode(event);",
    onfocus: "getFocus(event);"
  },
  {
    id: "tags",
    text: "Теги",
    icon: "fa-solid fa-tags",
    objectClass: "prsTag",
    tabindex: "0",
    onclick: "clickNode(event);",
    onfocus: "getFocus(event);"
  },
  {
    id: "connectors",
    text: "Коннекторы",
    icon: "fa-solid fa-link",
    objectClass: "prsConnector",
    tabindex: "0",
    onclick: "clickNode(event);",
    onfocus: "getFocus(event);"
  },
  {
    id: "schedules",
    icon: "fa-solid fa-clock",
    text: "Расписания",
    objectClass: "prsSchedule",
    tabindex: "0",
    onclick: "clickNode(event);",
    onfocus: "getFocus(event);"
  }
];

var topNodesIds = topNodes.map((node) => {
  return node.id;
})

/*
var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
  return new bootstrap.Tooltip(tooltipTriggerEl)
});
*/

const baseIndent = 1.5;
const parentsMarginLeft = 0.25;
const options = {
  data: topNodes,
  expandIcon: 'fa fa-angle-down fa-fw',
  collapseIcon: 'fa fa-angle-right fa-fw',
  indent: baseIndent,
  parentsMarginLeft: `${parentsMarginLeft}rem`,
  openNodeLinkOnNewTab: true
}
const int_attrs = ["prsIndex", "prsValueTypeCode", "prsEntityTypeCode"];
const bool_attrs = ["prsActive", "prsStep", "prsUpdate", "prsDefault"]

$('#tree').bstreeview(options);
// ----------------------------------------------------------------------------------------------------------------------------

saveChanges = () => {
  let nodeId = $("#div-nodeId").text();
  let objectClass = $(".currentNode").attr("objectClass");
  let url = window.location.protocol + "//" + window.location.hostname + apis[objectClass];
  let changedElements = [...$(".value-changed")];

  let payload = {
    id: nodeId,
    attributes: {}
  }

  let cnChanged = false;
  let error_prepare_data = false;
  changedElements.map((element) => {
    attr = element.getAttribute("prsAttribute");
    if (attr === "parameter")
      return
    if (attr === "cn")
      cnChanged = true;

    if ((attr !== "initiatedBy") && (attr !== "alertConfig") && (attr !== "scheduleConfig")) {
      if (int_attrs.includes(attr) && (element.value !== null)) {
        payload.attributes[attr] = Number(element.value);
      } else if (bool_attrs.includes(attr) && (element.value !== null)) {
        payload.attributes[attr] = element.value === 'true';
      } else
        payload.attributes[attr] = element.value;
    } else if (attr === "alertConfig") {
      payload.attributes["prsJsonConfigString"] = {
        high: $("#input-alertConfHigh").val() === 'true',
        value: Number($("#input-alertConfValue").val()),
        autoAck: $("#input-alertConfAutoack").val() === 'true'
      }
    } else if (attr === "scheduleConfig") {
      ts = {}
      if ($("#input-scheduleConfStart").val() !== '') {
        dt = new Date(Date.parse($("#input-scheduleConfStart").val()));
        ts.start = dt.toISOString();
      }
      if ($("#input-scheduleConfIntervalType").val())
        ts.interval_type = $("#input-scheduleConfIntervalType").val()
      if ($("#input-scheduleConfIntervalValue").val())
        ts.interval_value = Number($("#input-scheduleConfIntervalValue").val())
      if ($("#input-scheduleConfEnd").val() !== '') {
        dt = new Date(Date.parse($("#input-scheduleConfEnd").val()));
        ts.end = dt2.toISOString();
      }
      payload.attributes["prsJsonConfigString"] = ts
    }
  });

  if (objectClass === "prsMethod") {
    let initiatedBy = [];

    // если меняется метод, то надо собрать всех инициаторов, независимо от того, что изменилось
    $("#input-initiatedByTags > option").each(function () {
      if (this.selected) {
        initiatedBy.push(this.value);
      }
    });
    $("#input-initiatedBySchedules > option").each(function () {
      if (this.selected)
        initiatedBy.push(this.value);
    });
    payload.initiatedBy = initiatedBy;

    parameters = []
    //...а также параметры
    $("#div-list-parameters > div").each(function () {
      index = this.id.split("-").slice(-1);

      let parameter_payload = {};
      try {
        parameter_payload = JSON.parse($(`#input-parameter-prsJsonConfigString-${index}`).val());
      } catch (err) {
        showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", `Ошибка конвертирования данных параметра: '${err}'`);
        error_prepare_data = true;
        return
      }

      parameters.push({
        attributes: {
          cn: $(`#input-parameter-cn-${index}`).val(),
          prsIndex: $(`#input-parameter-prsIndex-${index}`).val(),
          prsJsonConfigString: parameter_payload
        }
      });
    });
    if (parameters.length > 0)
      payload.parameters = parameters;
  }

  if (error_prepare_data)
    return;

  fetch(url, {
    method: "PUT",
    body: JSON.stringify(payload),
    headers: new Headers({
      'Content-Type': 'application/json'
    })
  }).then((response) => {
    if (!response.ok) {
      throw response;
    }

    if (cnChanged) {
      $("#div-nodeName").text(payload.attributes.cn);
      $(`#${payload.id}`).contents().last().replaceWith(payload.attributes.cn);
    }
    changedElements.map((element) => {
      element.setAttribute("init-value", element.value);
      element.classList.remove("value-changed");
    });
    $("#but-save").addClass("disabled");
    $("#but-reset").addClass("disabled");

    changeTagDataPanelOnSave();

  }).catch((err) => {
    err.json().then((body) => {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateDataAlert", `Ошибка обновления узла '${JSON.stringify(body)}'`);
    })
  });
};

addParameter = (event, parameterData) => {
  getTagsPayload = {
    base: "prs",
    deref: false,
    scope: 2,
    filter: {
      objectClass: ["prsTag"]
    },
    attributes: ["cn", "objectClass"]
  }
  params = new URLSearchParams({ q: JSON.stringify(getTagsPayload) }).toString();

  url = `${window.location.protocol}//${window.location.hostname}/v1/objects/?${params}`;
  fetch(url).then((response) => {
    if (!response.ok) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка получения списка тегов, тревог, расписаний.", false);
      return;
    }

    return response.json();
  }).then((data) => {
    if (!data) return;
    
    divParameters = document.getElementById("div-list-parameters");
    lastSpanParameter = divParameters.lastElementChild;

    lastLevel = -1;
    if (lastSpanParameter) {
      lastLevel = Number(lastSpanParameter.getAttribute("prsIndex"));
    }
    newLevel = lastLevel + 1;

    $("#div-list-parameters").append(`
      <div class="d-flex align-items-center" prsIndex="${newLevel}" id="span-parameter-${newLevel}">
        <div class="col-1 me-2">
          <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="number" id="input-parameter-prsIndex-${newLevel}"/>
        </div>
        <div class="col-1 me-2">
          <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-cn-${newLevel}"/>
        </div>
        <div class="col-4 me-2">
          <select prsAttribute="parameter" onchange="onInputChange(event);" id="input-parameter-tagId-${newLevel}" class="form-select form-select-sm" size="1">
            <option selected value="ttt">&#62;=</option>
            <option value="ttttt">&#60;</option>											
          </select>
        </div>
        <div class="col me-2">
          <!--
          <input class="form-control form-control-sm" prsAttribute="parameter" onchange="onInputChange(event);" type="text" id="input-parameter-prsJsonConfigString-${newLevel}"/>
          -->
          <textarea class="form-control form-control-sm" prsAttribute="parameter" autocomplete="off" rows="1" id="input-parameter-prsJsonConfigString-${newLevel}"></textarea>
        </div>
        <button id="but-deleteParameter-${newLevel}" class="btn btn-sm m-1 btn-danger" onclick="deleteParameter(event);">
          <span><i class="fa-solid fa-minus" id="i-deleteParameter-${newLevel}"></i></span>
        </button>
      </div>
    `);

    allTags = data.data;
    level = newLevel;
    tags = [];
    parameter_tags_select = $(`#input-parameter-tagId-${level}`);
    $(`#input-parameter-tagId-${level} option`).remove();
    allTags.map((dataItem) => {
      tags.push({
        cn: dataItem.attributes.cn[0],
        id: dataItem.id
      });
    });
    tags.map((el) => {
      parameter_tags_select.append(`<option value="${el.id}">${el.cn}&nbsp;(${el.id})</option>`);
    });
    parameter_tags_select.val("");
    if (parameterData) {
      let index = Number(parameterData.attributes.prsIndex[0]);
      let name = parameterData.attributes.cn[0];
      let config_text = parameterData.attributes.prsJsonConfigString[0];
  
      let config = JSON.parse(config_text);
      if (Array.isArray(config.tagId))
        tagId = config.tagId[0];
      else
        tagId = config.tagId;
  
      parameter_tags_select.val(tagId);
  
      $(`#input-parameter-prsIndex-${level}`).val(index);
      $(`#input-parameter-cn-${level}`).val(name);
      $(`#input-parameter-prsJsonConfigString-${level}`).val(config_text);
    }
  });
}

deleteParameter = (event) => {
  event.stopPropagation();
  targetEl = event.target;
  deletedId = targetEl.id;
  if (deletedId.startsWith("i-"))
    targetEl.parentElement.parentElement.parentElement.remove();
  else
    targetEl.parentElement.remove();
}

deleteNode = () => {
  let currentNode = $(".currentNode")[0];
  let nodeId = currentNode.id;
  let objectClass = currentNode.getAttribute("objectClass");
  let url = window.location.protocol + "//" + window.location.hostname + apis[objectClass];
  fetch(url, {
    method: "DELETE",
    body: JSON.stringify({ id: nodeId }),
    headers: new Headers({
      'Content-Type': 'application/json'
    })
  }).then((response) => {
    if (!response.ok) {
      throw response;
    };

    let group = getNodeGroup(currentNode);
    if (group) {
      group.remove();
    }
    currentNode.remove();
  }).catch((err) => {
    err.json().then((body) => {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", `Ошибка удаления узла '${nodeId}': '${JSON.stringify(body)}'`);
    })
  });;
};

onInputChange = (event) => {
  targetEl = event.target;
  initValue = targetEl.getAttribute("init-value");
  let equal = false;

  if (targetEl.tagName === "SELECT") {
    let curVal = $(targetEl).val()

    if (Array.isArray(curVal))
      curVal.join(',');
    equal = initValue === curVal;
  } else
    equal = (initValue === $(targetEl).val())

  if (equal)
    targetEl.classList.remove("value-changed");
  else
    targetEl.classList.add("value-changed");

  // если изменился тег из списка тегов в параметре
  elId = targetEl.id;
  if (elId.startsWith("input-parameter-tagId")) {
    let paramIndex = elId.split("-").slice(-1);
    selectedTag = $(targetEl).val();
    payload = {
      tagId: [selectedTag]
    }
    $(`#input-parameter-prsJsonConfigString-${paramIndex}`).val(
      JSON.stringify(payload, null, "\t")
    ).addClass("value-changed");
  }

  inputs = document.querySelectorAll(".value-changed");
  if (inputs.length > 0) {
    $("#but-save").removeClass("disabled");
    $("#but-reset").removeClass("disabled");
  } else {
    $("#but-save").addClass("disabled");
    $("#but-reset").addClass("disabled");
  }


};

getFocus = (event) => {
  event.stopPropagation();

  els = document.getElementsByClassName("currentNode");
  elsArray = [...els];
  elsArray.map((el) => {
    el.classList.toggle("currentNode");
  });
  el = event.target;
  el.classList.toggle("currentNode");
};

sortList = (group) => {
  var new_group = group.cloneNode(false);
  // Add all lis to an array
  var groupItems = [];
  for (var i = 0; i < group.childNodes.length; i++) {
    if (group.childNodes[i].getAttribute("role") === 'treeitem')
      groupItems.push(group.childNodes[i]);
  }
  // Sort the lis in descending order
  groupItems.sort((a, b) => {
    res = 1;

    if ((a.getAttribute("objectClass") == "prsObject") &&
      (b.getAttribute("objectClass") == "prsTag")) {
      res = -1;
    } else if ((a.getAttribute("objectClass") == "prsTag") &&
      (b.getAttribute("objectClass") == "prsObject")) {
      res = 1;
    } else if (a.textContent < b.textContent) {
      res = -1;
    } else {
      res = 1;
    }

    return res;
  });

  for (var i = 0; i < groupItems.length; i++) {
    new_group.appendChild(groupItems[i]);
    //dataBsTargetId = groupItems[i].getAttribute("data-bs-target").substring(1);
    //itemGroup = document.getElementById(dataBsTargetId);
    //if (itemGroup) new_group
  }

  if (group.parentNode !== null) {
    group.parentNode.replaceChild(new_group, group);
  };
};

addNode = (parentElement, node, top = false) => {
  // добавление узла в иерархию
  // parentElement - родительский элемент
  // node - {
  //  id: "...",
  //  text: "...",
  //  icon: "....",
  //  objectClass: "...",
  // }
  // top - добавлять в начало списка

  // атрибут data-bs-target у узла всегда создаётся, но вот 
  // элемента, на который он указывает, может и не быть
  parentGroupId = parentElement.getAttribute("data-bs-target").substring(1);
  parentGroup = document.getElementById(parentGroupId);
  if (!parentGroup) {
    parentGroup = document.createElement("div");
    parentGroup.setAttribute("role", "group");
    parentGroup.setAttribute("class", "list-group collapse show");
    parentGroup.setAttribute("id", parentGroupId);

    parentElement.parentNode.insertBefore(parentGroup, parentElement.nextSibling);

    icon = parentElement.querySelector('.state-icon');
    if (!icon) {
      icon = document.createElement("i");
      parentElement.insertBefore(icon, parentElement.firstChild);
    }
    icon.setAttribute("class", `state-icon ${options.expandIcon}`);
  }

  parentAreaLevel = Number(parentElement.getAttribute("aria-level"));

  itemDiv = document.createElement("div");
  itemDiv.setAttribute("id", node.id);
  itemDiv.setAttribute("role", "treeitem");
  itemDiv.setAttribute("class", "list-group-item");
  itemDiv.setAttribute("data-bs-toggle", "collapse");
  itemDiv.setAttribute("data-bs-target", `#group_${node.id}`);
  padding = parentsMarginLeft + baseIndent * parentAreaLevel;
  itemDiv.setAttribute("style", `padding-left:${padding}rem`);
  itemDiv.setAttribute("aria-level", `${parentAreaLevel + 1}`);
  itemDiv.setAttribute("objectClass", node.objectClass);
  itemDiv.setAttribute("tabindex", "0");
  switch (node.objectClass) {
    case "prsObject":
    case "prsTag":
    case "prsAlert":
    case "prsMethod":
      itemDiv.classList.add(node.objectClass);
  }
  itemDiv.setAttribute("onclick", "clickNode(event);");
  itemDiv.setAttribute("onfocus", "getFocus(event);");

  if ((top) && (parentGroup.children.length > 0)) {
    parentGroup.insertBefore(itemDiv, parentGroup.firstChild);
  } else {
    parentGroup.appendChild(itemDiv);
  };

  if (node.icon) {
    icon = document.createElement("i");
    icon.setAttribute("class", `item-icon ${node.icon}`);
    itemDiv.append(icon)
  }
  itemDiv.append(node.text);

  return itemDiv;
}

// возвращает группу узла, в которой находятся его дети
getNodeGroup = (nodeElement) => {
  dataBsTargetId = nodeElement.getAttribute("data-bs-target").substring(1);
  return document.getElementById(dataBsTargetId);
};

const typeNames = {
  "prsObject": "Объект",
  "prsTag": "Тег",
  "prsAlert": "Тревога",
  "prsMethod": "Метод",
  "prsConnector": "Коннектор",
  "prsSchedule": "Расписание"
}

const visibility = {
  "prsObject": {
    "visible": ["div-prsIndex"], // имя, описание, индекс, активный - видны всегда
    "hidden": ["div-prsMethodAddress", "div-prsValueTypeCode", "div-tagData",
      "div-prsJsonConfigString", "div-prsUpdate", "div-prsDefault", "div-prsStep",
      "div-prsMeasureUnits", "div-initiatedBy", "div-parameters", "div-alertConfig", "div-scheduleConfig", "div-prsEntityTypeCode"]
  },
  "prsTag": {
    "visible": ["div-prsValueTypeCode", "div-prsUpdate", "div-prsStep", "div-prsMeasureUnits", "div-tagData"],
    "hidden": ["div-prsIndex", "div-prsMethodAddress", "div-prsDefault", "div-prsJsonConfigString",
      "div-initiatedBy", "div-parameters", "div-alertConfig", "div-scheduleConfig", "div-prsEntityTypeCode"]
  },
  "prsAlert": {
    "visible": ["div-alertConfig"],
    "hidden": ["div-prsIndex", "div-prsMethodAddress", "div-prsDefault",
      "div-prsUpdate", "div-prsStep", "div-prsMeasureUnits", "div-prsValueTypeCode",
      "div-initiatedBy", "div-parameters", "div-prsJsonConfigString", "div-scheduleConfig", "div-prsEntityTypeCode", "div-tagData"]
  },
  "prsMethod": {
    "visible": ["div-prsMethodAddress", "div-initiatedBy", "div-parameters"],
    "hidden": ["div-prsIndex", "div-prsEntityTypeCode", "div-prsJsonConfigString", "div-prsDefault",
      "div-prsUpdate", "div-prsStep", "div-prsMeasureUnits", "div-prsValueTypeCode", "div-alertConfig", "div-scheduleConfig", "div-tagData"]
  },
  "prsConnector": {
    "visible": ["div-prsJsonConfigString"],
    "hidden": ["div-prsIndex", "div-prsMethodAddress", "div-prsEntityTypeCode", "div-prsDefault",
      "div-prsUpdate", "div-prsStep", "div-prsMeasureUnits", "div-prsValueTypeCode",
      "div-initiatedBy", "div-parameters", "div-alertConfig", "div-scheduleConfig", "div-tagData"]
  },
  "prsSchedule": {
    "visible": ["div-scheduleConfig"],
    "hidden": ["div-prsIndex", "div-prsDefault",
      "div-prsUpdate", "div-prsStep", "div-prsMeasureUnits", "div-prsValueTypeCode",
      "div-prsMethodAddress", "div-initiatedBy", "div-parameters", "div-alertConfig", "div-prsJsonConfigString", "div-prsEntityTypeCode", "div-tagData"
    ]
  }
}

const apis = {
  "prsObject": "/v1/objects/",
  "prsTag": "/v1/tags/",
  "prsAlert": "/v1/alerts/",
  "prsMethod": "/v1/methods/",
  "prsConnector": "/v1/connectors/",
  "prsSchedule": "/v1/schedules/"
}

setAttributesVisibility = (nodeElement) => {
  nodeId = nodeElement.id;
  objClass = nodeElement.getAttribute("objectClass");

  attributesForm = document.getElementById('attributes-form');
  if (topNodesIds.includes(nodeId)) {
    attributesForm.classList.add("d-none");
    return;
  }
  attributesForm.classList.remove("d-none");

  visibility[objClass]["hidden"].map((div) => {
    document.getElementById(div).classList.add('d-none');
  })
  visibility[objClass]["visible"].map((div) => {
    document.getElementById(div).classList.remove('d-none');
  })
};

setAddButtonsVisibility = (clickedNode) => {
  objClass = clickedNode.getAttribute("objectClass");
  nodeId = clickedNode.id;
  switch (objClass) {
    case "prsObject":
      $("#but-newObject").removeClass("d-none");
      $("#but-newAlert").addClass("d-none");
      $("#but-newMethod").addClass("d-none");
      $("#but-newSchedule").addClass("d-none");
      $("#but-newConnector").addClass("d-none");
      if (nodeId === "objects") {
        $("#but-delNode").addClass("d-none");
        $("#but-newTag").addClass("d-none");
      } else {
        $("#but-delNode").removeClass("d-none");
        $("#but-newTag").removeClass("d-none");
      }
      break;
    case "prsTag":
      $("#but-newObject").addClass("d-none");
      $("#but-newSchedule").addClass("d-none");
      $("#but-newConnector").addClass("d-none");
      if (nodeId === "tags") {
        $("#but-delNode").addClass("d-none");
        $("#but-newTag").removeClass("d-none");
        $("#but-newAlert").addClass("d-none");
        $("#but-newMethod").addClass("d-none");
      } else {
        $("#but-delNode").removeClass("d-none");
        $("#but-newTag").addClass("d-none");
        $("#but-newAlert").removeClass("d-none");
        $("#but-newMethod").removeClass("d-none");
      }
      break;
    case "prsAlert":
      $("#but-newObject").addClass("d-none");
      $("#but-newTag").addClass("d-none");
      $("#but-newAlert").addClass("d-none");
      $("#but-newMethod").removeClass("d-none");
      $("#but-newSchedule").addClass("d-none");
      $("#but-newConnector").addClass("d-none");
      $("#but-delNode").removeClass("d-none");
      break;
    case "prsMethod":
      $("#but-newObject").addClass("d-none");
      $("#but-newTag").addClass("d-none");
      $("#but-newAlert").addClass("d-none");
      $("#but-newMethod").addClass("d-none");
      $("#but-newSchedule").addClass("d-none");
      $("#but-newConnector").addClass("d-none");
      $("#but-delNode").removeClass("d-none");
      break;
    case "prsSchedule":
      $("#but-newObject").addClass("d-none");
      $("#but-newAlert").addClass("d-none");
      $("#but-newTag").addClass("d-none");
      $("#but-newMethod").addClass("d-none");
      $("#but-newConnector").addClass("d-none");
      if (nodeId === "schedules") {
        $("#but-delNode").addClass("d-none");
        $("#but-newSchedule").removeClass("d-none");

      } else {
        $("#but-delNode").removeClass("d-none");
        $("#but-newSchedule").addClass("d-none");
      }
      break;
    case "prsConnector":
      $("#but-newObject").addClass("d-none");
      $("#but-newAlert").addClass("d-none");
      $("#but-newTag").addClass("d-none");
      $("#but-newMethod").addClass("d-none");
      $("#but-newSchedule").addClass("d-none");
      if (nodeId === "connectors") {
        $("#but-delNode").addClass("d-none");
        $("#but-newConnector").removeClass("d-none");

      } else {
        $("#but-delNode").removeClass("d-none");
        $("#but-newConnector").addClass("d-none");
      }
      break;
  }
};

showAlert = (divAlertId, divAlertMessageId, icon, message, norm) => {
  $(`#${divAlertMessageId}`).text(message);
  $(`#${divAlertId}`).removeClass("d-none");
  if (norm) {
    $(`#${divAlertId}`).removeClass("alert-danger");
    $(`#${divAlertId}`).addClass("alert-success");

    $(`#${icon}`).removeClass("fa-solid fa-circle-exclamation");
    $(`#${icon}`).addClass("fas fa-check-circle");

  } else {
    $(`#${divAlertId}`).addClass("alert-danger");
    $(`#${divAlertId}`).removeClass("alert-success");

    $(`#${icon}`).addClass("fa-solid fa-circle-exclamation");
    $(`#${icon}`).removeClass("fas fa-check-circle");
  }

  setTimeout(() => {
    $(`#${divAlertId}`).addClass("d-none");
  }, 5000);
}

var newNodeId = null;

addNodeToHierarchy = (api) => {

  if (api === 'connectors') {
    showAlert("div-butAlert", "div-butAlertMessage", "i-butAlert",
      'Работа с коннекторами - в следующей версии конфигуратора.', true);
    return;
  }

  url = window.location.protocol + "//" + window.location.hostname + "/v1/" + api + "/";

  parentId = $("div.currentNode")[0].id;

  payload = { attributes: {} };
  if (!((parentId === "objects") || (parentId === "tags") || (parentId === "connectors") || (parentId === "schedules"))) {
    payload.parentId = parentId;
  }

  fetch(url, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: new Headers({
      'Content-Type': 'application/json'
    })
  }).then((response) => {
    if (response.status !== 201) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", `Ошибка создания нового узла: ${JSON.stringify(response.json())}`, false);
      return;
    }
    return response.json();
  }).then((data) => {
    if (!data)
      return;
    new_id = data.id;
    url += `?q=${encodeURIComponent(JSON.stringify({
      id: new_id,
      attributes: ["cn", "objectClass"]
    }))}`;
    fetch(url, {
      headers: {
        "Content-type": "application/json",
      }
    }).then((response) => {
      if (response.status !== 200) {
        showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", `Ошибка получения данных по вновь созданному объекту ${new_id}`, false);
        return;
      }
      return response.json();
    }).then((data) => {
      if (!data)
        return;

      divToExtend = document.getElementById(parentId);
      node = {
        id: new_id,
        text: data.data[0].attributes.cn[0],
        objectClass: data.data[0].attributes.objectClass[0]
      };
      switch (node.objectClass) {
        case "prsObject":
          node.icon = "fa-solid fa-object-ungroup prsObject";
          break;
        case "prsTag":
          node.icon = "fa-solid fa-tag prsTag";
          break;
        case "prsAlert":
          node.icon = "fa-solid fa-bell prsAlert";
          break;
        case "prsMethod":
          node.icon = "fa-solid fa-file-code prsMethod";
          break;
        case "prsConnector":
          node.icon = "fa-solid fa-link prsConnector";
          break;
        case "prsSchedule":
          node.icon = "fa-solid fa-clock prsSchedule";
          break;
      }

      // привяжем тег к хранилищу
      if ((api === "tags") || (api === "alerts")) {
        urlDs = window.location.protocol + "//" + window.location.hostname + "/v1/dataStorages/";

        payload = { base: "", attributes: ["cn"] };
        urlDsGet = urlDs + `?q=${encodeURIComponent(JSON.stringify(payload))}`;
        fetch(urlDsGet, {
          headers: {
            "Content-type": "application/json",
          }
        }).then((response) => {
          if (response.status !== 200) {
            showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", `Ошибка получения данных по хранилищу ${new_id}`, false);
            return;
          }
          return response.json();
        }).then((data) => {
          if (!data)
            return;
          payload = {
            id: data.data[0].id
          }
          if (api === "tags") {
            payload.linkTags = [{ tagId: node.id }]
          } else {
            payload.linkAlerts = [{ alertId: node.id }]
          }

          fetch(urlDs, {
            method: "PUT",
            body: JSON.stringify(payload),
            headers: new Headers({
              'Content-Type': 'application/json'
            })
          }).then((response) => {
            if (response.status !== 202) {
              showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", `Ошибка получения данных по хранилищу ${JSON.stringify(response.json())}`, false);
              return;
            }
          })
        })
      }

      if (!($("div.currentNode").attr("aria-expanded"))) {

        var clickEvent = new MouseEvent("click", {
          "view": window,
          "bubbles": true,
          "cancelable": false
        });
        $("div.currentNode").removeClass("currentNode");
        newNodeId = new_id;
        el = document.getElementById(parentId);
        el.dispatchEvent(clickEvent);

      } else
        var new_node = addNode(divToExtend, node, true);

      var clickEvent = new MouseEvent("click", {
        "view": window,
        "bubbles": true,
        "cancelable": false
      });
      new_node.dispatchEvent(clickEvent);
      new_node.focus();
    })
  });
};

var tagGetDataURL = '';
var tagGetDataPayload = {};
var tagSetDataURL = '';
var tagSetDataPayload = {};
getTagData = () => {
  tagGetDataURL = $("#span-tagGetDataURL").text();
  fetch(tagGetDataURL, {
    headers: {
      "Content-type": "application/json",
    }
  }).then((response) => {
    if (response.status !== 200) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", `Ошибка получения данных тега '${tagGetDataPayload.tagId}'`, false);
      return;
    }
    return response.json();
  }).then((data) => {
    tagData = data.data[0].data;

    tBody = $("#tbody-tagData").empty();
    tagData.map((dataItem) => {
      tr = $("<tr></tr>").appendTo(tBody);
      tr.append(`<td>${JSON.stringify(dataItem[0])}</td><td>${dataItem[1]}</td><td>${dataItem[2]}</td>`);
    });
  });
}

setTagData = () => {
  tagSetDataPayload = JSON.parse($("#span-tagSetDataBody").text());
  tagSetDataURL = `${window.location.protocol}//${window.location.hostname}/v1/data/`;
  fetch(tagSetDataURL, {
    method: "POST",
    body: JSON.stringify(tagSetDataPayload),
    headers: new Headers({
      'Content-Type': 'application/json'
    })
  }).then((response) => {
    if (!response.ok) {
      showAlert("div-setDataAlert", "div-setDataAlertMessage", "i-setDataAlert", `Ошибка обновления данных '${body}'`, false);
    } else {
      showAlert("div-setDataAlert", "div-setDataAlertMessage", "i-setDataAlert", `Данные успешно записаны.`, true);
    }
  })
}

changeTagDataPanelOnSave = () => {
  tBody = $("#tbody-tagData").empty();
  value_type = Number($("#input-prsValueTypeCode").val());
  input_el = $("#input-tagSetDataValue");
  input_el.val(null);
  switch (value_type) {
    case 0:
    case 1:
      input_el.attr("type", "number");
      break;
    case 2:
      input_el.attr("type", "text");
      break;
    case 4:
      input_el.attr("type", "textarea");
      break;
  }
}

tagSetDataValueChanged = () => {
  value_type = Number($("#input-prsValueTypeCode").attr("init-value"));
  value = $("#input-tagSetDataValue").val();
  switch (value_type) {
    case 4:
      try {
        value = JSON.parse(value);
      } catch (err) {
        showAlert("div-setDataAlert", "div-setDataAlertMessage", "i-setDataAlert", `Ошибка конвертирования json: ${err}`, false);
        $("#input-tagSetDataValue").val(null);
        tagSetDataPayload = {
          data: [
            {
              tagId: $("#div-nodeId").text(),
              data: [[null]]
            }
          ]
        }
        $("#span-tagSetDataBody").text(JSON.stringify(tagSetDataPayload, null, "\t"));
        return;
      }
      break;

    case 0:
    case 1:
      try {
        value = Number(value);
      } catch (err) {
        showAlert("div-setDataAlert", "div-setDataAlertMessage", "i-setDataAlert", `Ошибка конвертирования числа: ${err}`, false);
        $("#input-tagSetDataValue").val(null);
        tagSetDataPayload = {
          data: [
            {
              tagId: $("#div-nodeId").text(),
              data: [[null]]
            }
          ]
        }
        $("#span-tagSetDataBody").text(JSON.stringify(tagSetDataPayload, null, "\t"));
        return;
      }
  }

  tagSetDataPayload = {
    data: [
      {
        tagId: $("#div-nodeId").text(),
        data: [[value]]
      }
    ]
  }

  $("#span-tagSetDataBody").text(JSON.stringify(tagSetDataPayload, null, "\t"));
}

formTagDataPanels = () => {
  let post_url = `${window.location.protocol}//${window.location.hostname}/v1/data/`;
  let get_url = `${post_url}?q=`;
  tagGetDataPayload = {
    tagId: $("#div-nodeId").text()
  }

  format = $("#input-tagGetDataFormat").is(":checked");
  if (format)
    tagGetDataPayload.format = true;

  actual = $("#input-tagGetDataActual").is(":checked");
  if (actual)
    tagGetDataPayload.actual = true;

  tagGetDataURL = `${get_url}${JSON.stringify(tagGetDataPayload)}`
  $("#span-tagGetDataURL").text(tagGetDataURL);

  $("#tbody-tagData").empty();

  tagSetDataURL = post_url;
  tagSetDataPayload = {
    data: [
      {
        tagId: $("#div-nodeId").text(),
        data: [[null]]
      }
    ]
  }
  $("#span-tagSetDataURL").text(tagSetDataURL);
  $("#span-tagSetDataBody").text(JSON.stringify(tagSetDataPayload, null, "\t"));
}

// используем этот список при заполнении списка тегов в параметрах
var tags = [];

fillForm = (nodeElement) => {
  let nodeId = nodeElement.id;
  let header = document.getElementById("div-nodeName");
  header.innerText = nodeElement.innerText;

  let attrsType = document.getElementById("div-nodeType");
  let objClass = nodeElement.getAttribute("objectClass");
  attrsType.innerText = typeNames[objClass];

  let attrsId = document.getElementById("div-nodeId");
  attrsId.innerText = nodeId;

  let payload = {
    id: nodeId,
    attributes: ["cn", "objectClass", "description", "prsActive", "prsArchive", "prsCompress",
      "prsDefault", "prsStep", "prsUpdate", "prsValueTypeCode", "prsEntityTypeCode", "prsIndex",
      "prsJsonConfigString", "prsMeasureUnits", "prsMethodAddress"],
    getParent: true
  }

  let params = new URLSearchParams({ q: JSON.stringify(payload) }).toString();

  let api = apis[objClass];
  if (!api) return;

  let url = `${window.location.protocol}//${window.location.hostname}${api}?${params}`;

  fetch(url).then((response) => {
    if (response.status !== 200) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", `Ошибка чтения данных: ${JSON.stringify(response.json())}`, false);
      return;
    }
    return response.json();
  }).then((data) => {
    if (data.data.length == 0) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", `Нет данных по узлу ${nodeElement.innerText}`, false);
      return;
    }

    nodeData = data.data[0];
    Object.entries(nodeData.attributes).map((entry) => {
      value = "";
      switch (entry[1][0]) {
        case "TRUE":
          value = "true"
          break;
        case "FALSE":
          value = "false";
          break;
        default:
          value = (entry[1][0] === null) ? "" : entry[1][0]
      }

      if ((objClass === "prsAlert") && (entry[0] === "prsJsonConfigString")) {
        conf = JSON.parse(value);
        $("#input-alertConfHigh").attr("init-value", conf.high).val(conf.high.toString());
        $("#input-alertConfValue").attr("init-value", conf.value).val(conf.value);
        $("#input-alertConfAutoack").attr("init-value", conf.autoAck).val(conf.autoAck.toString());
      } else if ((objClass === "prsSchedule") && (entry[0] === "prsJsonConfigString")) {
        // много кода из-за кривизны работы javascript с метками времени, точнее - с временными зонами
        conf = JSON.parse(value);
        dt = new Date(Date.parse(conf.start));
        ms = dt.getTimezoneOffset() * 60000;
        dt2 = new Date(dt.getTime() - ms);
        $("#input-scheduleConfStart").attr("init-value", dt2.toISOString().substring(0, 16)).val(dt2.toISOString().substring(0, 16));
        $("#input-scheduleConfIntervalType").attr("init-value", conf.interval_type).val(conf.interval_type);
        $("#input-scheduleConfIntervalValue").attr("init-value", conf.interval_value).val(conf.interval_value);
        if (("end" in conf) && (conf.end)) {
          dt = new Date(Date.parse(conf.end));
          ms = dt.getTimezoneOffset() * 60000;
          dt2 = new Date(dt.getTime() - ms);
          $("#input-scheduleConfEnd").attr("init-value", dt2.toISOString().substring(0, 16)).val(dt2.toISOString().substring(0, 16));
        } else $("#input-scheduleConfEnd").attr("init-value", null);
      } else {
        element = document.getElementById(`input-${entry[0]}`);
        if (element) {
          element.value = value;
          element.setAttribute("init-value", value);
        }
      }
    });

    // для метода - заполним список initiatedBy и parameters
    if (objClass === "prsMethod") {
      $("#input-initiatedByTags option").remove();
      $("#input-initiatedByAlerts option").remove();
      $("#input-initiatedBySchedules option").remove();
      let getTagsAlertsSchedulesPayload = {
        base: "prs",
        deref: false,
        scope: 2,
        filter: {
          objectClass: ["prsTag", "prsAlert", "prsSchedule"]
        },
        attributes: ["cn", "objectClass"]
      }
      let params = new URLSearchParams({ q: JSON.stringify(getTagsAlertsSchedulesPayload) }).toString();

      let url = `${window.location.protocol}//${window.location.hostname}/v1/objects/?${params}`;
      fetch(url).then((response) => {
        if (!response.ok) {
          showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", "Ошибка получения списка тегов, тревог, расписаний.", false);
          return;
        }
        return response.json();
      }).then((allNodes) => {
        if (!allNodes) return;
        let selectId = "";
        allNodes.data.map((dataItem) => {
          switch (dataItem.attributes.objectClass[0]) {
            case "prsTag":
              selectId = "#input-initiatedByTags";              
              break;
            case "prsAlert":
              selectId = "#input-initiatedByAlerts";
              break;
            case "prsSchedule":
              selectId = "#input-initiatedBySchedules";
          };

          let selected = nodeData.initiatedBy.includes(dataItem.id);
          let disabled = dataItem.id === nodeData.parentId;
          if (selected)
            $(selectId).append(`<option selected value="${dataItem.id}">${dataItem.attributes.cn[0]}&nbsp;(${dataItem.id})</option>`);
          else
            if (!disabled)
              $(selectId).append(`<option value="${dataItem.id}">${dataItem.attributes.cn[0]}&nbsp;(${dataItem.id})</option>`);
        });

        $("#input-initiatedByTags").attr("init-value", $("#input-initiatedByTags").val());
        $("#input-initiatedByAlerts").attr("init-value", $("#input-initiatedByAlerts").val());
        $("#input-initiatedBySchedules").attr("init-value", $("#input-initiatedBySchedules").val());

        // параметры
        $("#div-list-parameters").empty();
        nodeData.parameters.map((item) => {
          addParameter(null, item);
        });
      })
    }

    // для тега подготовим панели работы с данными
    if (objClass === "prsTag")
      changeTagDataPanelOnSave();
    formTagDataPanels();
  });
};

removeClassOnElements = (styleClass) => {
  const elements = document.querySelectorAll(`.${styleClass}`);

  elements.forEach((element) => {
    element.classList.remove(styleClass);
  });
}

resetChanges = () => {
  const elements = document.querySelectorAll(`.value-changed`);
  els = [...elements];
  els.map((el) => {
    initValue = el.getAttribute("init-value");
    el.value = initValue;
    el.classList.remove("value-changed");
  });
  $("#but-reset").addClass("disabled");
  $("#but-save").addClass("disabled");
};

clickNode = (event) => {
  event.stopPropagation();

  let clickedNode = event.target;

  removeClassOnElements("value-changed");

  setAttributesVisibility(clickedNode);

  setAddButtonsVisibility(clickedNode);

  let expanded = clickedNode.getAttribute("aria-expanded");
  if (expanded) {
    clickedNode.removeAttribute("aria-expanded");
    let group = getNodeGroup(clickedNode);
    if (group) {
      group.remove();

      let icon = clickedNode.querySelector(".state-icon");
      if (icon) {
        icon.className = `state-icon ${options.collapseIcon}`;
      }

      return;
    }
  }
  clickedNode.setAttribute("aria-expanded", "true");
  let clickedObjectClass = clickedNode.getAttribute("objectClass");
  let clickedId = clickedNode.id;

  let api = apis[clickedObjectClass];

  if (!api) return;

  let payload = {
    base: "",
    attributes: ["cn", "objectClass"],
    filter: { objectClass: ["prsObject", "prsMethod", "prsTag", "prsAlert", "prsConnector", "prsSchedule"] },
    scope: 1,
    hierarchy: true,
  }

  if (!((clickedId === "objects") || (clickedId === "tags")
    || (clickedId === "connectors") || (clickedId === "schedules"))) {
    payload.base = clickedId;
    fillForm(clickedNode);
  }

  let params = new URLSearchParams({ q: JSON.stringify(payload) }).toString();

  let url = `${window.location.protocol}//${window.location.hostname}${api}?${params}`;

  fetch(url).then((response) => {
    if (response.status !== 200) {
      showAlert("div-updateAlert", "div-updateAlertMessage", "i-updateAlert", `Ошибка чтения данных: ${JSON.stringify(response.json())}`, false);
      return;
    }
    return response.json();
  }).then((data) => {
    data.data.map((nodeItem) => {
      node = {
        id: nodeItem.id,
        text: nodeItem.attributes.cn[0],
        objectClass: nodeItem.attributes.objectClass[0]
      };
      switch (node.objectClass) {
        case "prsObject":
          node.icon = "fa-solid fa-object-ungroup prsObject";
          break;
        case "prsTag":
          node.icon = "fa-solid fa-tag prsTag";
          break;
        case "prsAlert":
          node.icon = "fa-solid fa-bell prsAlert";
          break;
        case "prsMethod":
          node.icon = "fa-solid fa-file-code prsMethod";
          break;
        case "prsConnector":
          node.icon = "fa-solid fa-link prsConnector";
          break;
        case "prsSchedule":
          node.icon = "fa-solid fa-clock prsSchedule";
          break;
      };
      addNode(clickedNode, node);
    });

    groupItems = getNodeGroup(clickedNode);
    if (groupItems) sortList(groupItems);

    if (newNodeId) {
      var new_node = document.getElementById(newNodeId);
      newNodeId = null;
      var clickEvent = new MouseEvent("click", {
        "view": window,
        "bubbles": true,
        "cancelable": false
      });
      new_node.dispatchEvent(clickEvent);
      new_node.focus();
      /*
      $(`#${newNodeId}`).addClass("currentNode");
      fillForm(document.getElementById(newNodeId));
      newNodeId = null;
      */
    }
  });
};
