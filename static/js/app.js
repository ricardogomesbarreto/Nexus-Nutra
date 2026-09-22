(() => {
  "use strict";

  document.querySelectorAll("[data-dismiss]").forEach((button) => {
    button.addEventListener("click", () => button.closest(".flash")?.remove());
  });

  const menuButton = document.querySelector("[data-menu-toggle]");
  const sidebar = document.querySelector("#sidebar");
  menuButton?.addEventListener("click", () => sidebar?.classList.toggle("open"));
  document.addEventListener("click", (event) => {
    if (window.innerWidth <= 900 && sidebar?.classList.contains("open") && !sidebar.contains(event.target) && !menuButton.contains(event.target)) {
      sidebar.classList.remove("open");
    }
  });

  const roleForm = document.querySelector("[data-role-form]");
  if (roleForm) {
    const syncRole = () => {
      const role = roleForm.querySelector("input[name='role']:checked")?.value;
      const professional = roleForm.querySelector("[data-nutritionist-field]");
      const patient = roleForm.querySelector("[data-patient-field]");
      professional?.classList.toggle("hidden", role !== "nutritionist");
      patient?.classList.toggle("hidden", role !== "patient");
      const crn = professional?.querySelector("input");
      if (crn) crn.required = role === "nutritionist";
    };
    roleForm.querySelectorAll("input[name='role']").forEach((input) => input.addEventListener("change", syncRole));
    syncRole();
  }

  document.querySelectorAll("[data-range]").forEach((range) => {
    const output = range.closest("label")?.querySelector("[data-range-value]");
    const update = () => { if (output) output.textContent = range.value; };
    range.addEventListener("input", update);
    update();
  });

  const modeSelect = document.querySelector("[data-mode-select]");
  if (modeSelect) {
    const onlineField = document.querySelector("[data-online-field]");
    const syncMode = () => onlineField?.classList.toggle("hidden", modeSelect.value !== "online");
    modeSelect.addEventListener("change", syncMode);
    syncMode();
  }

  const messages = document.querySelector("[data-messages]");
  if (messages) messages.scrollTop = messages.scrollHeight;

  const planForm = document.querySelector("[data-plan-form]");
  if (planForm) {
    const container = planForm.querySelector("[data-food-items]");
    const nutrientNames = ["calories", "protein", "carbs", "fat", "fiber", "calcium", "iron", "sodium", "saturated_fat", "sugars"];
    const catalogNode = planForm.querySelector("[data-food-catalog]");
    const catalog = catalogNode ? JSON.parse(catalogNode.textContent || "[]") : [];
    const clinicalNode = planForm.querySelector("[data-clinical-context]");
    const clinical = clinicalNode ? JSON.parse(clinicalNode.textContent || "{}") : {};
    const normalize = (value) => value.trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");
    const catalogByName = new Map(catalog.map((food) => [normalize(food.name), food]));
    const clinicalText = normalize(Object.values(clinical).join(" "));
    const syncAlerts = () => {
      const matches = [];
      container.querySelectorAll("[data-food-search]").forEach((input) => {
        const food = catalogByName.get(normalize(input.value || ""));
        String(food?.allergens || "").split(",").forEach((raw) => {
          const allergen = raw.trim();
          if (allergen && clinicalText.includes(normalize(allergen))) matches.push(`${food.name}: ${allergen}`);
        });
      });
      const panel = planForm.querySelector("[data-plan-alerts]");
      const text = planForm.querySelector("[data-plan-alert-text]");
      panel?.classList.toggle("hidden", matches.length === 0);
      if (text) text.textContent = matches.length ? `Revise ${[...new Set(matches)].join("; ")}.` : "";
    };
    const renumber = () => {
      container.querySelectorAll("[data-food-row]").forEach((row, index) => {
        const number = row.querySelector("[data-row-number]");
        if (number) number.textContent = String(index + 1);
        const remove = row.querySelector("[data-remove-food]");
        if (remove) remove.disabled = container.querySelectorAll("[data-food-row]").length === 1;
      });
    };
    const totals = () => nutrientNames.forEach((name) => {
      const total = [...container.querySelectorAll(`[data-nutrient='${name}']`)]
        .reduce((sum, input) => sum + (Number.parseFloat(input.value) || 0), 0);
      const output = planForm.querySelector(`[data-total='${name}']`);
      if (output) output.textContent = name === "calories" ? String(Math.round(total)) : total.toFixed(1);
    });
    const calculateRow = (row) => {
      const search = row.querySelector("[data-food-search]");
      const amount = Number.parseFloat(row.querySelector("[data-amount-g]")?.value) || 0;
      const food = catalogByName.get(normalize(search?.value || ""));
      const foodId = row.querySelector("[data-food-id]");
      const status = row.querySelector("[data-catalog-status]");
      const source = row.querySelector("[data-food-source]");
      if (!food) {
        if (foodId) foodId.value = "";
        if (status) status.textContent = "Preenchimento manual";
        if (source) source.textContent = "Alimento fora do catálogo: informe os nutrientes manualmente.";
        totals(); syncAlerts();
        return;
      }
      if (foodId) foodId.value = String(food.id);
      if (status) status.textContent = "Catálogo TACO";
      if (source) source.textContent = food.source + " · " + food.household_measure;
      if (amount > 0) {
        nutrientNames.forEach((name) => {
          const input = row.querySelector("[data-nutrient='" + name + "']");
          if (input) input.value = ((Number(food[name]) || 0) * amount / 100).toFixed(1);
        });
      }
      totals(); syncAlerts();
    };
    const bindRow = (row) => {
      row.querySelectorAll("[data-nutrient]").forEach((input) => input.addEventListener("input", totals));
      row.querySelector("[data-food-search]")?.addEventListener("change", () => calculateRow(row));
      row.querySelector("[data-amount-g]")?.addEventListener("input", () => calculateRow(row));
      row.querySelector("[data-remove-food]")?.addEventListener("click", () => {
        if (container.querySelectorAll("[data-food-row]").length > 1) {
          row.remove(); renumber(); totals(); syncAlerts();
        }
      });
    };
    container.querySelectorAll("[data-food-row]").forEach(bindRow);
    planForm.querySelector("[data-add-food]")?.addEventListener("click", () => {
      const original = container.querySelector("[data-food-row]");
      const clone = original.cloneNode(true);
      clone.querySelectorAll("input").forEach((input) => {
        input.value = input.hasAttribute("data-nutrient") ? "0" : "";
      });
      const status = clone.querySelector("[data-catalog-status]");
      const source = clone.querySelector("[data-food-source]");
      if (status) status.textContent = "Preenchimento manual";
      if (source) source.textContent = "Selecione um alimento do catálogo para cálculo automático.";
      bindRow(clone); container.appendChild(clone); renumber(); totals();
      clone.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    renumber(); totals(); syncAlerts();
  }

  const recipeForm = document.querySelector("[data-recipe-form]");
  if (recipeForm) {
    const catalogNode = recipeForm.querySelector("[data-recipe-catalog]");
    const catalog = catalogNode ? JSON.parse(catalogNode.textContent || "[]") : [];
    const byId = new Map(catalog.map((food) => [String(food.id), food]));
    const container = recipeForm.querySelector("[data-recipe-items]");
    const calculate = () => {
      const totals = { calories: 0, protein: 0, carbs: 0, fat: 0 };
      container.querySelectorAll("[data-recipe-row]").forEach((row) => {
        const food = byId.get(row.querySelector("select")?.value || "");
        const amount = Number.parseFloat(row.querySelector("input")?.value) || 0;
        Object.keys(totals).forEach((field) => { totals[field] += (Number(food?.[field]) || 0) * amount / 100; });
      });
      Object.entries(totals).forEach(([field, value]) => {
        const output = recipeForm.querySelector(`[data-recipe-total='${field}']`);
        if (output) output.textContent = field === "calories" ? String(Math.round(value)) : value.toFixed(1);
      });
    };
    const bind = (row) => {
      row.querySelectorAll("select, input").forEach((input) => input.addEventListener("input", calculate));
      row.querySelector("[data-remove-recipe-item]")?.addEventListener("click", () => {
        if (container.querySelectorAll("[data-recipe-row]").length > 1) row.remove();
        calculate();
      });
    };
    container.querySelectorAll("[data-recipe-row]").forEach(bind);
    recipeForm.querySelector("[data-add-recipe-item]")?.addEventListener("click", () => {
      const clone = container.querySelector("[data-recipe-row]").cloneNode(true);
      clone.querySelectorAll("select, input").forEach((input) => { input.value = ""; });
      bind(clone); container.appendChild(clone); calculate();
    });
    calculate();
  }

  const chart = document.querySelector("#progressChart");
  if (chart) {
    const values = JSON.parse(chart.dataset.values || "[]").map(Number);
    const labels = JSON.parse(chart.dataset.labels || "[]");
    const draw = () => {
      const rect = chart.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      chart.width = Math.max(300, rect.width) * ratio;
      chart.height = Math.max(180, rect.height) * ratio;
      const ctx = chart.getContext("2d");
      ctx.scale(ratio, ratio);
      const width = chart.width / ratio;
      const height = chart.height / ratio;
      const pad = { top: 22, right: 22, bottom: 34, left: 44 };
      ctx.clearRect(0, 0, width, height);
      if (!values.length) return;
      const min = Math.min(...values) - 1;
      const max = Math.max(...values) + 1;
      ctx.strokeStyle = "#e4ebe6"; ctx.lineWidth = 1;
      ctx.fillStyle = "#829087"; ctx.font = "11px DM Sans";
      for (let step = 0; step <= 4; step += 1) {
        const y = pad.top + ((height - pad.top - pad.bottom) * step / 4);
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
        const label = (max - ((max - min) * step / 4)).toFixed(1);
        ctx.fillText(label, 4, y + 4);
      }
      const xFor = (index) => pad.left + (values.length === 1 ? (width - pad.left - pad.right) / 2 : index * (width - pad.left - pad.right) / (values.length - 1));
      const yFor = (value) => pad.top + (max - value) * (height - pad.top - pad.bottom) / (max - min || 1);
      const gradient = ctx.createLinearGradient(0, pad.top, 0, height - pad.bottom);
      gradient.addColorStop(0, "rgba(25,122,80,.23)"); gradient.addColorStop(1, "rgba(25,122,80,0)");
      ctx.beginPath(); values.forEach((value, index) => index ? ctx.lineTo(xFor(index), yFor(value)) : ctx.moveTo(xFor(index), yFor(value)));
      ctx.lineTo(xFor(values.length - 1), height - pad.bottom); ctx.lineTo(xFor(0), height - pad.bottom); ctx.closePath(); ctx.fillStyle = gradient; ctx.fill();
      ctx.beginPath(); values.forEach((value, index) => index ? ctx.lineTo(xFor(index), yFor(value)) : ctx.moveTo(xFor(index), yFor(value)));
      ctx.strokeStyle = "#197a50"; ctx.lineWidth = 2.5; ctx.lineJoin = "round"; ctx.stroke();
      values.forEach((value, index) => {
        ctx.beginPath(); ctx.arc(xFor(index), yFor(value), 4, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill(); ctx.strokeStyle = "#197a50"; ctx.lineWidth = 2; ctx.stroke();
        if (labels[index] && (values.length <= 7 || index % Math.ceil(values.length / 7) === 0 || index === values.length - 1)) {
          const parts = labels[index].split("-"); const label = parts.length === 3 ? `${parts[2]}/${parts[1]}` : labels[index];
          ctx.fillStyle = "#829087"; ctx.textAlign = "center"; ctx.fillText(label, xFor(index), height - 10);
        }
      });
    };
    draw();
    let timer;
    window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(draw, 120); });
  }
})();
