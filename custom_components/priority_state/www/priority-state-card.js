class PriorityStateCard extends HTMLElement {
  constructor() {
    super();
    this._mode = "view";
    this._editRuleId = null;
  }

  setConfig(config) {
    this._config = config;
  }

  set hass(hass) {
    if (!this._initialized) {
      this._hass = hass;
      this._init();
      this._initialized = true;
    }
    this._hass = hass;
    this._update();
  }

  _init() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="card-content"></div>
      </ha-card>
      <style>
        .header {
          padding: 16px 16px 8px;
          font-size: 18px;
          font-weight: 500;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .header-actions {
          display: flex;
          gap: 6px;
          align-items: center;
        }
        .light-status {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          font-weight: 400;
          padding: 0 16px 12px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          flex-wrap: wrap;
        }
        .color-dot {
          display: inline-block;
          width: 14px;
          height: 14px;
          border-radius: 50%;
          border: 1px solid var(--divider-color, #e0e0e0);
          flex-shrink: 0;
        }
        .winner-badge {
          font-size: 10px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          background: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, #fff);
          padding: 2px 6px;
          border-radius: 3px;
        }
        .debug-badge {
          font-size: 10px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          background: var(--error-color, #db4437);
          color: var(--text-primary-color, #fff);
          padding: 2px 6px;
          border-radius: 3px;
        }
        .rules-list {
          padding: 4px 0;
        }
        .rule-row {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 16px;
          min-height: 40px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .rule-row:last-child {
          border-bottom: none;
        }
        .rule-row.winner {
          background: rgba(3, 169, 244, 0.08);
        }
        .rule-swatch {
          width: 24px;
          height: 24px;
          border-radius: 4px;
          border: 1px solid var(--divider-color, #e0e0e0);
          flex-shrink: 0;
        }
        .rule-info {
          flex: 1;
          min-width: 0;
        }
        .rule-name {
          font-size: 14px;
          font-weight: 500;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .rule-meta {
          font-size: 11px;
          color: var(--secondary-text-color, #888);
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
        }
        .disabled-label {
          font-size: 10px;
          font-weight: 600;
          text-transform: uppercase;
          color: var(--error-color, #db4437);
          letter-spacing: 0.5px;
        }
        .entity-indicator {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          font-weight: 500;
          padding: 4px 8px;
          border-radius: 4px;
          flex-shrink: 0;
        }
        .entity-indicator.on {
          color: var(--primary-color, #03a9f4);
        }
        .entity-indicator.off {
          color: var(--disabled-text-color, #999);
        }
        .entity-indicator .state-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .entity-indicator.on .state-dot {
          background: var(--primary-color, #03a9f4);
        }
        .entity-indicator.off .state-dot {
          background: var(--disabled-text-color, #999);
        }
        .no-rules {
          padding: 24px 16px;
          text-align: center;
          color: var(--secondary-text-color, #888);
          font-size: 14px;
        }
        .btn {
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          border: none;
          border-radius: 4px;
          padding: 5px 10px;
          cursor: pointer;
          background: var(--secondary-background-color, #e0e0e0);
          color: var(--primary-text-color, #000);
          white-space: nowrap;
        }
        .btn:hover {
          filter: brightness(0.85);
        }
        .btn-primary {
          background: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, #fff);
        }
        .btn-danger {
          background: var(--error-color, #db4437);
          color: var(--text-primary-color, #fff);
        }
        .btn-sm {
          font-size: 10px;
          padding: 3px 7px;
        }
        .toolbar {
          display: flex;
          gap: 8px;
          padding: 8px 16px 4px;
          flex-wrap: wrap;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .form {
          padding: 16px;
        }
        .form-row {
          margin-bottom: 12px;
        }
        .form-row label {
          display: block;
          font-size: 12px;
          font-weight: 500;
          margin-bottom: 4px;
          color: var(--secondary-text-color, #888);
        }
        .form-row input,
        .form-row select {
          width: 100%;
          box-sizing: border-box;
          padding: 8px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 4px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #000);
          font-size: 14px;
        }
        .form-row input[type="color"] {
          width: 48px;
          height: 36px;
          padding: 2px;
          cursor: pointer;
        }
        .form-row input[type="checkbox"] {
          width: auto;
          margin-top: 4px;
        }
        .form-actions {
          display: flex;
          gap: 8px;
          margin-top: 16px;
        }
      </style>
    `;
    this.shadowRoot.addEventListener("click", (ev) => {
      const target = ev.target;
      if (target.closest(".toggle-btn")) {
        const btn = target.closest(".toggle-btn");
        const entity = btn.dataset.entity;
        const action = btn.dataset.actionType;
        this._hass.callService("homeassistant", action, { entity_id: entity });
        return;
      }
      if (target.closest("[data-action='add']")) {
        this._mode = "add";
        this._editRuleId = null;
        this._formEntityId = "";
        this._update();
        return;
      }
      if (target.closest("[data-action='edit']")) {
        const ruleId = target.closest("[data-action='edit']").dataset.ruleId;
        this._mode = "edit";
        this._editRuleId = ruleId;
        this._formEntityId = "";
        this._update();
        return;
      }
      if (target.closest("[data-action='delete']")) {
        const ruleId = target.closest("[data-action='delete']").dataset.ruleId;
        const ruleName = target.closest("[data-action='delete']").dataset.ruleName;
        if (confirm(`Delete rule "${ruleName}"?`)) {
          this._hass.callService("priority_state", "remove_rule", { rule_id: ruleId });
        }
        return;
      }
      if (target.closest("[data-action='cancel']")) {
        this._mode = "view";
        this._editRuleId = null;
        this._update();
        return;
      }
      if (target.closest("[data-action='clear']")) {
        if (confirm("Clear ALL rules?")) {
          this._hass.callService("priority_state", "clear_rules", {});
        }
        return;
      }
      if (target.closest("[data-action='save']")) {
        this._handleSave();
        return;
      }
    });
  }

  _getSensor() {
    return Object.values(this._hass.states).find(
      (s) => s.attributes && Array.isArray(s.attributes.rules)
    );
  }

  _update() {
    const content = this.shadowRoot.querySelector(".card-content");
    if (this._mode === "view") {
      content.innerHTML = this._renderView();
    } else {
      content.innerHTML = this._renderForm();
    }
  }

  _renderView() {
    const sensor = this._getSensor();
    if (!sensor) {
      return `<div class="no-rules">Priority State sensor not found</div>`;
    }
    const attr = sensor.attributes;
    const rules = attr.rules || [];
    const targetLight = attr.target_light;
    const lightState = attr.light_state;
    const lightColor = attr.light_color;
    const winnerId = attr.winner;
    const winnerName = attr.winner_name;
    const isDebug = attr.debug;

    let lightColorHex = "";
    if (lightColor && lightState === "on") {
      lightColorHex = this._hsToHex(lightColor);
    }

    let html = "";
    html += `<div class="header">`;
    html += `  <span>Priority State${isDebug ? ' <span class="debug-badge">DEBUG</span>' : ""}</span>`;
    html += `  <span class="header-actions">`;
    html += `    <button class="btn btn-primary btn-sm" data-action="add">+ Add</button>`;
    if (rules.length) {
      html += `    <button class="btn btn-sm" data-action="clear">Clear</button>`;
    }
    html += `  </span>`;
    html += `</div>`;

    html += `<div class="light-status">`;
    html += `  Target: ${this._escape(targetLight || "Not set")}`;
    if (targetLight) {
      const dotColor = lightState === "on" ? (lightColorHex || "#03a9f4") : "#ccc";
      html += `  <span class="color-dot" style="background:${dotColor}"></span>`;
      html += `  ${lightState === "on" ? "On" : "Off"}`;
      if (winnerName) {
        html += `  <span class="winner-badge">${this._escape(winnerName)}</span>`;
      }
    }
    html += `</div>`;

    if (rules.length === 0) {
      html += `<div class="no-rules">No rules configured.</div>`;
    } else {
      const sorted = [...rules].sort((a, b) => a.priority - b.priority);
      html += `<div class="rules-list">`;
      for (const rule of sorted) {
        const isWinner = rule.id === winnerId;
        const isEnabled = rule.enabled !== false;
        const entityState = this._hass.states[rule.entity_id];
        const isOn = entityState && entityState.state === "on";
        const swatchColor = this._hsToHex(rule.hs_color);

        html += `<div class="rule-row${isWinner ? " winner" : ""}">`;
        html += `  <div class="rule-swatch" style="background:${swatchColor}"></div>`;
        html += `  <div class="rule-info">`;
        html += `    <div class="rule-name">${this._escape(rule.name)}</div>`;
        html += `    <div class="rule-meta">`;
        html += `      P${rule.priority} &middot; ${this._escape(rule.entity_id)}`;
        if (!isEnabled) {
          html += `      <span class="disabled-label">Disabled</span>`;
        }
        html += `    </div>`;
        html += `  </div>`;
        html += `  <div class="entity-indicator ${isOn ? "on" : "off"}">`;
        html += `    <span class="state-dot"></span>`;
        html += `    ${isOn ? "ON" : "OFF"}`;
        if (isDebug) {
          const action = isOn ? "turn_off" : "turn_on";
          html += `    <button class="btn btn-sm toggle-btn" data-entity="${this._escape(rule.entity_id)}" data-action-type="${action}">Toggle</button>`;
        }
        html += `  </div>`;
        html += `  <button class="btn btn-sm" data-action="edit" data-rule-id="${rule.id}">Edit</button>`;
        html += `  <button class="btn btn-sm btn-danger" data-action="delete" data-rule-id="${rule.id}" data-rule-name="${this._escape(rule.name)}">Del</button>`;
        html += `</div>`;
      }
      html += `</div>`;
    }
    return html;
  }

  _renderForm() {
    const sensor = this._getSensor();
    const isAdd = this._mode === "add";
    let rule = null;
    if (!isAdd && sensor) {
      const rules = sensor.attributes.rules || [];
      rule = rules.find((r) => r.id === this._editRuleId);
    }

    const name = rule ? rule.name : "";
    const entityId = rule ? rule.entity_id : "";
    const priority = rule ? rule.priority : 1;
    const colorHex = rule ? this._hsToHex(rule.hs_color) : "#ffffff";
    const enabled = rule ? (rule.enabled !== false) : true;

    let html = "";
    html += `<div class="form">`;
    html += `  <h3 style="margin:0 0 16px;font-size:16px;font-weight:500;">${isAdd ? "Add Rule" : "Edit Rule"}</h3>`;
    html += `  <div class="form-row">`;
    html += `    <label>Name</label>`;
    html += `    <input id="f-name" type="text" value="${this._escape(name)}" placeholder="My rule">`;
    html += `  </div>`;
    const entityOptions = Object.keys(this._hass.states)
      .sort()
      .map((e) => `<option value="${this._escape(e)}">`)
      .join("");
    html += `  <div class="form-row">`;
    html += `    <label>Entity</label>`;
    html += `    <input id="f-entity" type="text" list="entity-list" value="${this._escape(entityId)}" placeholder="binary_sensor.something">`;
    html += `    <datalist id="entity-list">${entityOptions}</datalist>`;
    html += `  </div>`;
    html += `  <div class="form-row">`;
    html += `    <label>Priority (lower = higher priority)</label>`;
    html += `    <input id="f-priority" type="number" value="${priority}" min="1" step="1">`;
    html += `  </div>`;
    html += `  <div class="form-row">`;
    html += `    <label>Color</label>`;
    html += `    <input id="f-color" type="color" value="${colorHex}">`;
    html += `  </div>`;
    html += `  <div class="form-row">`;
    html += `    <label>Enabled</label>`;
    html += `    <input id="f-enabled" type="checkbox"${enabled ? " checked" : ""}>`;
    html += `  </div>`;
    html += `  <div class="form-actions">`;
    html += `    <button class="btn btn-primary" data-action="save">Save</button>`;
    html += `    <button class="btn" data-action="cancel">Cancel</button>`;
    html += `  </div>`;
    html += `</div>`;
    return html;
  }

  _handleSave() {
    const root = this.shadowRoot;
    const name = root.getElementById("f-name").value.trim();
    const entityId = root.getElementById("f-entity").value.trim();
    const priority = parseInt(root.getElementById("f-priority").value, 10);
    const colorHex = root.getElementById("f-color").value;
    const enabled = root.getElementById("f-enabled").checked;
    const rgb = this._hexToRgb(colorHex);

    if (!name || !entityId) {
      alert("Name and Entity ID are required.");
      return;
    }
    if (isNaN(priority) || priority < 1) {
      alert("Priority must be a positive number.");
      return;
    }

    const serviceData = {
      name,
      entity_id: entityId,
      priority,
      rgb_color: rgb,
      enabled,
    };

    if (this._mode === "edit" && this._editRuleId) {
      serviceData.rule_id = this._editRuleId;
      this._hass.callService("priority_state", "update_rule", serviceData);
    } else {
      this._hass.callService("priority_state", "add_rule", serviceData);
    }

    this._mode = "view";
    this._editRuleId = null;
  }

  _hsToHex([h, s]) {
    const c = (s / 100) * 255;
    const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    const m = 255 - c;
    let r, g, b;
    if (h < 60) { r = c; g = x; b = 0; }
    else if (h < 120) { r = x; g = c; b = 0; }
    else if (h < 180) { r = 0; g = c; b = x; }
    else if (h < 240) { r = 0; g = x; b = c; }
    else if (h < 300) { r = x; g = 0; b = c; }
    else { r = c; g = 0; b = x; }
    const toHex = (v) => Math.round(Math.min(255, v + m)).toString(16).padStart(2, "0");
    return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
  }

  _hexToRgb(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return [r, g, b];
  }

  _escape(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  getCardSize() {
    const sensor = this._getSensor();
    const rules = sensor ? (sensor.attributes.rules || []).length : 0;
    return Math.max(1, rules + 2);
  }

  static getConfigElement() {
    return document.createElement("priority-state-card-editor");
  }

  static getStubConfig() {
    return {};
  }
}

class PriorityStateCardEditor extends HTMLElement {
  set hass(hass) { this._hass = hass; }
  setConfig(config) { this._config = config; }
  connectedCallback() {
    this.innerHTML = `
      <ha-card>
        <div class="card-content" style="padding:16px;color:var(--secondary-text-color);">
          Priority State card — no configuration needed.
        </div>
      </ha-card>
    `;
  }
}

customElements.define("priority-state-card", PriorityStateCard);
customElements.define("priority-state-card-editor", PriorityStateCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "priority-state-card",
  name: "Priority State",
  description: "View and manage priority state rules",
});
