export function validateProduct(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("На вход нужен один JSON-объект товара.");
  }
  const allowed = [
    "name",
    "manufacturer",
    "specs",
    "description",
    "source_url",
  ];
  const unexpected = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unexpected.length)
    throw new Error(
      "Неизвестные поля " +
        unexpected.join(", ") +
        ". Проверьте названия полей.",
    );
  const product = {
    name: "",
    manufacturer: "",
    specs: Object.create(null),
    description: "",
    source_url: "",
  };
  for (const [key, maxLength] of [
    ["name", 250],
    ["manufacturer", 150],
    ["description", 20000],
    ["source_url", 2000],
  ]) {
    const text = value[key] === undefined ? "" : value[key];
    if (typeof text !== "string")
      throw new Error("Поле " + key + " должно быть строкой.");
    if (text.trim().length > maxLength)
      throw new Error(
        "Поле " +
          key +
          " превышает допустимую длину " +
          maxLength +
          " символов.",
      );
    product[key] = text.trim();
  }
  if (!product.name)
    throw new Error(
      "Укажите название прибора. Остальные сведения можно оставить пустыми.",
    );
  const specs = value.specs === undefined ? {} : value.specs;
  if (!specs || typeof specs !== "object" || Array.isArray(specs))
    throw new Error("Поле specs должно быть JSON-объектом характеристик.");
  if (Object.keys(specs).length > 60)
    throw new Error("Допускается не более 60 характеристик.");
  for (const [rawName, rawValue] of Object.entries(specs)) {
    const name = rawName.trim();
    if (!name || name.length > 150)
      throw new Error(
        "Название характеристики должно содержать от 1 до 150 символов.",
      );
    if (
      Object.keys(product.specs).some(
        (key) => key.toLocaleLowerCase("ru") === name.toLocaleLowerCase("ru"),
      )
    )
      throw new Error("Характеристика «" + name + "» указана дважды.");
    if (rawValue !== null && typeof rawValue !== "string")
      throw new Error("Значение «" + name + "» должно быть строкой или null.");
    if (rawValue && rawValue.length > 2000)
      throw new Error("Значение «" + name + "» превышает 2000 символов.");
    product.specs[name] = rawValue?.trim() || null;
  }
  return product;
}

function assertUniqueKeys(source) {
  const stack = [];
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (char === "{" || char === "[")
      stack.push(char === "{" ? new Set() : null);
    else if (char === "}" || char === "]") stack.pop();
    else if (char === '"') {
      const start = index;
      for (index += 1; index < source.length; index += 1) {
        if (source[index] === "\\") index += 1;
        else if (source[index] === '"') break;
      }
      let next = index + 1;
      while (/\s/.test(source[next] || "") && next < source.length) next += 1;
      if (source[next] === ":") {
        const key = JSON.parse(source.slice(start, index + 1));
        const keys = stack.at(-1);
        if (keys.has(key))
          throw new Error(
            "Поле «" + key.slice(0, 150) + "» повторяется в JSON.",
          );
        keys.add(key);
      }
    }
  }
}

export function parseProductJSON(source) {
  if (new TextEncoder().encode(source).byteLength > 100000)
    throw new Error("Слишком большой JSON. Допускается до 100 КБ.");
  let value;
  try {
    value = JSON.parse(source);
  } catch (error) {
    const position = error.message.match(/position (\d+)/);
    let location = "";
    if (position) {
      const lines = source.slice(0, Number(position[1])).split("\n");
      location =
        " Строка " +
        lines.length +
        ", столбец " +
        (lines.at(-1).length + 1) +
        ".";
    }
    throw new Error(
      "Некорректный JSON." + location + " Проверьте кавычки, запятые и скобки.",
    );
  }
  assertUniqueKeys(source);
  return validateProduct(value);
}
