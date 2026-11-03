import { validateProduct, parseProductJSON } from "./input.mjs";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {
  examples: [],
  card: null,
  inputMode: "form",
  resultMode: "preview",
  sourceFingerprint: null,
  dirty: false,
  controller: null,
  timer: null,
};

function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    $("#toast").hidden = true;
  }, 3500);
}

function showError(selector, message) {
  const element = $(selector);
  element.textContent = message;
  element.hidden = false;
  element.focus();
}

function clearErrors() {
  ["#input-error", "#api-error"].forEach((selector) => {
    $(selector).hidden = true;
  });
  $("#source-name").removeAttribute("aria-invalid");
  $("#source-name").removeAttribute("aria-describedby");
}

function resizeTextarea(element) {
  if (!element.offsetParent) return;
  element.style.height = "0px";
  element.style.height = Math.ceil(element.scrollHeight + 2) + "px";
}

function resizeFields() {
  $$(".auto-size, .spec-name, .spec-value").forEach(resizeTextarea);
}

function readProduct() {
  if (state.inputMode === "json")
    return parseProductJSON($("#source-json").value);
  const specs = Object.create(null);
  for (const row of $$(".spec-row")) {
    const name = row.querySelector(".spec-name").value.trim();
    const value = row.querySelector(".spec-value").value.trim();
    if (!name && !value) continue;
    if (!name)
      throw new Error(
        "Добавьте название характеристики рядом со значением «" +
          value.slice(0, 40) +
          "».",
      );
    if (Object.hasOwn(specs, name))
      throw new Error("Характеристика «" + name + "» указана дважды.");
    specs[name] = value || null;
  }
  return validateProduct({
    name: $("#source-name").value,
    manufacturer: $("#source-manufacturer").value,
    specs,
    description: $("#source-description").value,
    source_url: $("#source-url").value,
  });
}

function fingerprint(product) {
  return JSON.stringify([
    product.name,
    product.manufacturer,
    Object.entries(product.specs).sort(([a], [b]) => a.localeCompare(b)),
    product.description,
    product.source_url,
  ]);
}

function updateSource(product) {
  try {
    const source = product || readProduct();
    const url = new URL(source.source_url);
    if (!["https:", "http:"].includes(url.protocol)) throw new Error();
    $("#source-link").href = url.href;
    $("#source-link").closest(".source-footnote").hidden = false;
    $("#review-source-name").textContent = url.hostname.replace(/^www\./, "");
  } catch {
    $("#source-link").closest(".source-footnote").hidden = true;
    $("#review-source-name").textContent = "Данные, введённые вручную";
  }
}

function setDirty() {
  try {
    const product = readProduct();
    state.dirty =
      !!state.card && fingerprint(product) !== state.sourceFingerprint;
    $("#input-error").hidden = true;
    $("#source-name").removeAttribute("aria-invalid");
    $("#source-name").removeAttribute("aria-describedby");
  } catch {
    state.dirty = !!state.card;
  }
  $("#stale-notice").hidden = !state.dirty;
  $("#reviewed-checkbox").checked = false;
  updateSource();
  updateSpecCount();
  updateChecks();
}

function updateSpecCount() {
  let count;
  if (state.inputMode === "json") {
    try {
      count = Object.keys(
        parseProductJSON($("#source-json").value).specs,
      ).length;
    } catch {
      $("#spec-count").textContent = "Проверьте JSON";
      return;
    }
  } else {
    count = $$(".spec-name").filter((element) => element.value.trim()).length;
  }
  $("#spec-count").textContent = "Параметров " + count;
}

function addSpec(name = "", value = "") {
  const row = document.createElement("div");
  row.className = "spec-row";
  const heading = document.createElement("div");
  heading.className = "spec-row-heading";
  const nameField = document.createElement("textarea");
  nameField.className = "spec-name";
  nameField.value = name;
  nameField.rows = 1;
  nameField.maxLength = 150;
  nameField.placeholder = "Название параметра";
  nameField.setAttribute("aria-label", "Название характеристики");
  const valueField = document.createElement("textarea");
  valueField.className = "spec-value";
  valueField.value = value || "";
  valueField.rows = 1;
  valueField.maxLength = 2000;
  valueField.placeholder = "Данных нет";
  valueField.setAttribute(
    "aria-label",
    name ? "Значение параметра " + name : "Значение характеристики",
  );
  const remove = document.createElement("button");
  remove.className = "remove-spec";
  remove.type = "button";
  remove.textContent = "×";
  remove.setAttribute("aria-label", "Удалить характеристику " + name);
  remove.addEventListener("click", () => {
    row.remove();
    updateSpecCount();
    setDirty();
  });
  for (const field of [nameField, valueField]) {
    field.addEventListener("input", () => {
      resizeTextarea(field);
      updateSpecCount();
      setDirty();
      valueField.setAttribute(
        "aria-label",
        "Значение параметра " + nameField.value,
      );
      remove.setAttribute(
        "aria-label",
        "Удалить характеристику " + nameField.value,
      );
    });
  }
  heading.append(nameField, remove);
  row.append(heading, valueField);
  $("#specs-table").append(row);
  updateSpecCount();
  requestAnimationFrame(() => {
    resizeTextarea(nameField);
    resizeTextarea(valueField);
  });
}

function fillForm(product) {
  $("#source-name").value = product.name;
  $("#source-manufacturer").value = product.manufacturer;
  $("#source-description").value = product.description;
  $("#source-url").value = product.source_url;
  $("#source-json").value = JSON.stringify(product, null, 2);
  $("#specs-table").replaceChildren();
  Object.entries(product.specs).forEach(([name, value]) =>
    addSpec(name, value),
  );
  if (!Object.keys(product.specs).length) addSpec();
  updateSource(product);
  requestAnimationFrame(resizeFields);
}

function setInputMode(mode) {
  if (mode === state.inputMode) return;
  clearErrors();
  let product;
  try {
    product = readProduct();
  } catch (error) {
    showError("#input-error", error.message);
    return;
  }
  if (mode === "json")
    $("#source-json").value = JSON.stringify(product, null, 2);
  else fillForm(product);
  state.inputMode = mode;
  updateSpecCount();
  $("#form-view").hidden = mode !== "form";
  $("#json-view").hidden = mode !== "json";
  for (const [id, selected] of [
    ["#form-tab", mode === "form"],
    ["#json-tab", mode === "json"],
  ]) {
    $(id).classList.toggle("selected", selected);
    $(id).setAttribute("aria-pressed", String(selected));
  }
  requestAnimationFrame(resizeFields);
}

function renderList(selector, values) {
  $(selector).replaceChildren();
  for (const value of values) {
    const item = document.createElement("li");
    item.textContent = value;
    $(selector).append(item);
  }
}

function renderDescription(text) {
  const paragraphs = text
    .split(/\n\s*\n/)
    .filter((paragraph) => paragraph.trim());
  $("#card-description").replaceChildren();
  for (const paragraph of paragraphs) {
    const element = document.createElement("p");
    element.textContent = paragraph.trim();
    $("#card-description").append(element);
  }
}

function modelLabel(id) {
  const labels = {
    "gpt-6.1-sol": "GPT-6.1 Sol",
    "gpt-5.5": "GPT-5.5",
    "gemini-3.6-flash": "Gemini 3.6 Flash",
    "qwen3.8-max": "Qwen3.8-Max",
    "kimi-k3": "Kimi K3",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
  };
  return labels[id] || id;
}

function renderCard() {
  const card = state.card;
  if (!card) return;
  $("#card-title").textContent = card.seo_title;
  renderDescription(card.seo_description);
  $("#card-specs").replaceChildren();
  for (const spec of card.key_specs) {
    const pair = document.createElement("div");
    pair.className =
      "spec-pair" + (spec.value === "данных нет" ? " missing" : "");
    const name = document.createElement("dt");
    const value = document.createElement("dd");
    name.textContent = spec.name;
    value.textContent = spec.value;
    pair.append(name, value);
    $("#card-specs").append(pair);
  }
  renderList("#card-queries", card.search_queries);
  $("#card-audience").textContent = card.commercial.audience;
  $("#card-tasks").textContent = card.commercial.tasks;
  renderList(
    "#missing-list",
    card.missing_data.length
      ? card.missing_data
      : ["Пропуски не отмечены. Сверьте полноту с паспортом."],
  );
  $("#missing-count").textContent = String(card.missing_data.length);
  renderList("#warnings-list", card.warnings);
  $("#warnings-section").hidden = !card.warnings.length;
  $("#reviewed-checkbox").checked = false;
  $("#copy-result").disabled = false;
  $("#download-result").disabled = false;
  updateChecks();
  updateRaw();
  $("#raw-output").scrollTop = 0;
}

function useExample() {
  const item = state.examples.find(
    (example) =>
      example.id === $('input[name="product-example"]:checked')?.value,
  );
  if (!item) return;
  clearErrors();
  const product = validateProduct(item.product);
  fillForm(product);
  state.sourceFingerprint = fingerprint(product);
  state.dirty = false;
  $("#stale-notice").hidden = true;
  if (item.saved_result) {
    state.card = structuredClone(item.saved_result.card);
    renderCard();
  } else {
    state.card = null;
    $("#card-title").textContent = product.name;
    renderDescription(
      "Создайте черновик по данным прибора. Сохранённого результата для этого товара пока нет.",
    );
    ["#card-specs", "#card-queries", "#format-checks"].forEach((selector) =>
      $(selector).replaceChildren(),
    );
    $("#card-audience").textContent = "Данных пока нет.";
    $("#card-tasks").textContent = "Данных пока нет.";
    $("#copy-result").disabled = true;
    $("#download-result").disabled = true;
  }
}

function editorialTextIsValid(card, product) {
  let prose = [
    card.seo_title,
    card.seo_description,
    ...card.search_queries,
    card.commercial.audience,
    card.commercial.tasks,
    ...card.missing_data,
    ...card.warnings,
  ].join("\n");
  for (const value of Object.values(product.specs)
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)) {
    prose = prose.split(value).join("");
  }
  prose = prose.replace(/(\d)\s*[–—]\s*(?=[+−-]?\d)/gu, "$1");
  return !/[:—–]/u.test(prose);
}

function updateChecks() {
  const card = state.card;
  if (!card) return;
  const titleLength = [...card.seo_title].length;
  const descriptionLength = [...card.seo_description].length;
  let product = null;
  try {
    product = readProduct();
  } catch {}
  const sparse =
    product &&
    card.status === "needs_data" &&
    !product.description &&
    Object.values(product.specs).filter(Boolean).length <= 2;
  const titleOK = titleLength > 0 && titleLength <= 70;
  const descriptionOK = descriptionLength >= 800 && descriptionLength <= 1200;
  const queriesOK =
    card.search_queries.length >= 3 &&
    card.search_queries.length <= 5 &&
    new Set(
      card.search_queries.map((query) => query.trim().toLocaleLowerCase("ru")),
    ).size === card.search_queries.length;
  const specsOK =
    product &&
    !state.dirty &&
    Object.entries(product.specs).every(([name, value]) =>
      card.key_specs.some(
        (spec) =>
          spec.name === name &&
          (value
            ? spec.value === value
            : spec.value === "данных нет" ||
              product.description.includes(spec.value)),
      ),
    );
  const styleOK = product && editorialTextIsValid(card, product);
  const rangesOK = !/\d\s*(?:\.{3}|…)\s*[+−-]?\d/u.test(
    [
      card.seo_description,
      card.commercial.audience,
      card.commercial.tasks,
    ].join(" "),
  );
  const paragraphsOK =
    sparse ||
    card.seo_description.split(/\n\s*\n/).filter((value) => value.trim())
      .length === 3;
  $("#title-counter").textContent = titleLength + " из 70";
  $("#description-counter").textContent = sparse
    ? descriptionLength + " символов / запрос уточнений"
    : descriptionLength + " / от 800 до 1200";
  $("#queries-counter").textContent =
    card.search_queries.length + " из допустимых 3–5";
  $("#title-counter").className = "counter " + (titleOK ? "valid" : "invalid");
  $("#description-counter").className =
    "counter " + (descriptionOK || sparse ? "valid" : "invalid");
  const checks = [
    [titleOK, "Заголовок до 70 символов"],
    [
      descriptionOK || sparse,
      sparse ? "Краткий запрос уточнений" : "Описание от 800 до 1200 символов",
    ],
    [queriesOK, "От 3 до 5 разных запросов"],
    [specsOK, "Характеристики совпадают с вводом"],
    [styleOK, "Без двоеточий и длинных тире"],
    [rangesOK, "Диапазоны в тексте записаны словами"],
    [
      paragraphsOK,
      sparse ? "Недостаток данных отмечен" : "Три смысловых абзаца",
    ],
  ];
  $("#format-checks").replaceChildren();
  for (const [ok, label] of checks) {
    const row = document.createElement("div");
    row.className = "check-item " + (ok ? "ok" : "warn");
    const icon = document.createElement("span");
    icon.textContent = ok ? "✓" : "!";
    row.append(icon, document.createTextNode(label));
    $("#format-checks").append(row);
  }
}

function toMarkdown(card) {
  const lines = [
    "# " + card.seo_title,
    "",
    card.seo_description,
    "",
    "## Характеристики",
    "",
  ];
  for (const spec of card.key_specs)
    lines.push("**" + spec.name + "**", "", spec.value, "");
  lines.push(
    "## Поисковые запросы",
    "",
    ...card.search_queries.map((query) => "- " + query),
    "",
    "## Для менеджера",
    "",
    "### Кому подходит",
    "",
    card.commercial.audience,
    "",
    "### Какие задачи решает",
    "",
    card.commercial.tasks,
  );
  if (card.missing_data.length)
    lines.push(
      "",
      "## Уточнить",
      "",
      ...card.missing_data.map((value) => "- " + value),
    );
  if (card.warnings.length)
    lines.push(
      "",
      "## Предупреждения",
      "",
      ...card.warnings.map((value) => "- " + value),
    );
  return lines.join("\n");
}

function updateRaw() {
  if (!state.card) return;
  $("#raw-output").textContent =
    state.resultMode === "json"
      ? JSON.stringify(state.card, null, 2)
      : toMarkdown(state.card);
  $("#copy-result").textContent =
    state.resultMode === "json" ? "Копировать JSON" : "Копировать Markdown";
}

async function requestJSON(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      "Нет связи с локальным сервером. Проверьте, что приложение запущено.",
    );
  }
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(
      "Сервер вернул некорректный ответ. Исходные данные и предыдущий черновик сохранены.",
    );
  }
  if (!response.ok) {
    const details = Array.isArray(result.details)
      ? result.details
          .map((item) =>
            typeof item === "string"
              ? item
              : [item.field, item.message].filter(Boolean).join(" "),
          )
          .join("; ")
      : "";
    throw new Error(
      [result.error || "Не удалось выполнить запрос.", details]
        .filter(Boolean)
        .join(" "),
    );
  }
  return result;
}

async function generate() {
  if (state.controller) return;
  clearErrors();
  let product;
  try {
    product = readProduct();
  } catch (error) {
    if (!$("#source-name").value.trim() && state.inputMode === "form") {
      $("#source-name").setAttribute("aria-invalid", "true");
      $("#source-name").setAttribute("aria-describedby", "input-error");
    }
    showError("#input-error", error.message);
    return;
  }
  const requestedFingerprint = fingerprint(product);
  const controller = new AbortController();
  state.controller = controller;
  const started = Date.now();
  $("#generate").disabled = true;
  $("#model-select").disabled = true;
  $("#request-status").hidden = false;
  const progress = document.createElement("span");
  const stop = document.createElement("button");
  stop.textContent = "Остановить ожидание";
  stop.addEventListener("click", () => controller.abort());
  $("#request-status").replaceChildren(progress, stop);
  const tick = () => {
    progress.textContent =
      "Готовим черновик / " + Math.floor((Date.now() - started) / 1000) + " с";
  };
  tick();
  state.timer = setInterval(tick, 1000);
  try {
    const result = await requestJSON("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product, model: $("#model-select").value }),
      signal: controller.signal,
    });
    state.card = result.card;
    state.sourceFingerprint = requestedFingerprint;
    try {
      state.dirty = fingerprint(readProduct()) !== requestedFingerprint;
    } catch {
      state.dirty = true;
    }
    $("#stale-notice").hidden = !state.dirty;
    renderCard();
    toast(
      state.dirty
        ? "Черновик создан для предыдущих исходных данных."
        : "Черновик создан. Проверьте уточнения.",
    );
  } catch (error) {
    showError(
      "#api-error",
      error.name === "AbortError"
        ? "Ожидание остановлено. Провайдер мог уже начать генерацию. Проверьте его журнал перед повтором."
        : error.message,
    );
  } finally {
    clearInterval(state.timer);
    state.controller = null;
    $("#request-status").hidden = true;
    $("#generate").disabled = false;
    $("#model-select").disabled = false;
  }
}

$("#form-tab").addEventListener("click", () => setInputMode("form"));
$("#json-tab").addEventListener("click", () => setInputMode("json"));
$("#load-example").addEventListener("click", useExample);
$("#add-spec").addEventListener("click", () => {
  addSpec();
  $("#specs-table").lastElementChild.querySelector(".spec-name").focus();
});
for (const selector of [
  "#source-name",
  "#source-manufacturer",
  "#source-description",
  "#source-url",
  "#source-json",
]) {
  $(selector).addEventListener("input", () => {
    if ($(selector).classList.contains("auto-size"))
      resizeTextarea($(selector));
    setDirty();
  });
}
for (const selector of ["#card-title", "#card-description"]) {
  $(selector).addEventListener("input", () => {
    if (!state.card) return;
    state.card.seo_title = $("#card-title").innerText.trim();
    state.card.seo_description = $("#card-description").innerText.trim();
    $("#reviewed-checkbox").checked = false;
    updateChecks();
    updateRaw();
  });
}
for (const button of $$(".result-tabs button")) {
  button.addEventListener("click", () => {
    state.resultMode = button.dataset.result;
    $("#raw-output").scrollTop = 0;
    for (const tab of $$(".result-tabs button")) {
      tab.classList.toggle("selected", tab === button);
      tab.setAttribute("aria-pressed", String(tab === button));
    }
    $("#card-preview").hidden = state.resultMode !== "preview";
    $("#raw-output").hidden = state.resultMode === "preview";
    updateRaw();
  });
}
$("#copy-result").addEventListener("click", async () => {
  if (!state.card) return;
  const text =
    state.resultMode === "json"
      ? JSON.stringify(state.card, null, 2)
      : toMarkdown(state.card);
  try {
    await navigator.clipboard.writeText(text);
    toast("Скопировано");
  } catch {
    toast("Копирование недоступно. Скачайте JSON кнопкой рядом.");
  }
});
$("#download-result").addEventListener("click", () => {
  if (!state.card) return;
  const blob = new Blob([JSON.stringify(state.card, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "product-card.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("JSON скачан");
});
$("#generate").addEventListener("click", generate);

let sourceWidth = 0;
const observer = new ResizeObserver((entries) => {
  const width = entries[0].contentRect.width;
  if (Math.abs(sourceWidth - width) > 1) {
    sourceWidth = width;
    requestAnimationFrame(resizeFields);
  }
});
observer.observe($(".source-panel"));
document.fonts.ready.then(resizeFields);

async function initialize() {
  const examples = requestJSON("/api/examples")
    .then((items) => {
      state.examples = items;
      $("#example-options").replaceChildren();
      for (const [index, item] of items.entries()) {
        const option = document.createElement("label");
        option.className = "example-option";
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "product-example";
        radio.value = item.id;
        radio.checked = index === 0;
        const name = document.createElement("span");
        name.textContent = item.product.name;
        option.append(radio, name);
        $("#example-options").append(option);
      }
      $("#load-example").disabled = items.length === 0;
      useExample();
    })
    .catch((error) => showError("#input-error", error.message));
  const models = requestJSON("/api/models")
    .then((data) => {
      if (data.models.length) {
        $("#model-select").replaceChildren();
        for (const model of data.models) {
          const option = document.createElement("option");
          option.value = model.id;
          option.textContent = modelLabel(model.id);
          $("#model-select").append(option);
        }
        if (
          ![...$("#model-select").options].some(
            (option) => option.value === data.default_model,
          )
        ) {
          const option = document.createElement("option");
          option.value = data.default_model;
          option.textContent = modelLabel(data.default_model);
          $("#model-select").prepend(option);
        }
      }
      $("#model-select").value = data.default_model;
    })
    .catch(() => {
      $("#model-note").textContent =
        "Каталог недоступен. Сохранена выбранная модель.";
    });
  await Promise.allSettled([examples, models]);
}
initialize();
