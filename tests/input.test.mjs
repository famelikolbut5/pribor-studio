import assert from "node:assert/strict";
import test from "node:test";
import { parseProductJSON, validateProduct } from "../app/static/input.mjs";

test("accepts a minimal product and supplies optional fields", () => {
  const product = parseProductJSON('{"name":"Прибор"}');
  assert.equal(product.name, "Прибор");
  assert.equal(product.manufacturer, "");
  assert.deepEqual(Object.keys(product.specs), []);
});

test("preserves technical values and treats empty specs as unknown", () => {
  const product = validateProduct({
    name: " Прибор ",
    specs: { " диапазон ": "-50–300 °C", питание: "  ", поверка: null },
  });
  assert.equal(product.name, "Прибор");
  assert.equal(product.specs.диапазон, "-50–300 °C");
  assert.equal(product.specs.питание, null);
  assert.equal(product.specs.поверка, null);
});

test("rejects malformed JSON without changing the source string", () => {
  const source = "{broken";
  assert.throws(() => parseProductJSON(source), /Некорректный JSON/);
  assert.equal(source, "{broken");
});

test("rejects arrays, null and missing names", () => {
  for (const source of ["[]", "null", "{}", '{"name":" "}'])
    assert.throws(() => parseProductJSON(source));
});

test("rejects repeated root keys instead of keeping the last value", () => {
  assert.throws(
    () => parseProductJSON('{"name":"A","name":"B"}'),
    /повторяется/,
  );
});

test("rejects repeated nested keys including escaped equivalents", () => {
  for (const source of [
    '{"name":"A","specs":{"x":"1","x":"2"}}',
    String.raw`{"name":"A","specs":{"x":"1","\u0078":"2"}}`,
  ])
    assert.throws(() => parseProductJSON(source), /повторяется/);
});

test("allows the same key in separate object scopes", () => {
  const product = parseProductJSON('{"name":"A","specs":{"name":"B"}}');
  assert.equal(product.specs.name, "B");
});

test("does not interpret quotes or braces inside data as object keys", () => {
  const description =
    'Текст {"name":"A","name":"B"} и кавычки \\" с путём C:\\file';
  const source = JSON.stringify({
    name: "A",
    description,
    specs: { артикул: 'A"B\\C' },
  });
  const product = parseProductJSON(source);
  assert.equal(product.description, description);
  assert.equal(product.specs.артикул, 'A"B\\C');
});

test("rejects semantic spec duplicates after whitespace and case normalization", () => {
  assert.throws(
    () =>
      validateProduct({
        name: "A",
        specs: { Питание: "24 В", " питание ": "220 В" },
      }),
    /дважды/,
  );
});

test("does not coerce numbers or booleans into technical strings", () => {
  for (const value of [0, 24, false, [], {}])
    assert.throws(() =>
      validateProduct({ name: "A", specs: { питание: value } }),
    );
  assert.equal(
    validateProduct({ name: "A", specs: { значение: "0" } }).specs.значение,
    "0",
  );
});

test("rejects unknown fields and null optional strings", () => {
  assert.throws(
    () => validateProduct({ name: "A", manufacturerr: "Testo" }),
    /Неизвестные поля/,
  );
  assert.throws(
    () => validateProduct({ name: "A", manufacturer: null }),
    /строкой/,
  );
});

test("enforces the input size and field limits before a request", () => {
  assert.throws(
    () =>
      parseProductJSON(
        JSON.stringify({ name: "A", description: "a".repeat(100001) }),
      ),
    /100 КБ/,
  );
  assert.throws(() => validateProduct({ name: "a".repeat(251) }));
  assert.throws(() =>
    validateProduct({
      name: "A",
      specs: Object.fromEntries(
        Array.from({ length: 61 }, (_, i) => ["k" + i, "v"]),
      ),
    }),
  );
  assert.throws(() =>
    validateProduct({ name: "A", specs: { x: "a".repeat(2001) } }),
  );
});

test("keeps prototype-like keys as ordinary data", () => {
  const product = parseProductJSON(
    '{"name":"A","specs":{"__proto__":"text","constructor":"text"}}',
  );
  assert.equal(Object.getPrototypeOf(product.specs), null);
  assert.equal(product.specs.__proto__, "text");
  assert.equal({}.polluted, undefined);
});

test("survives a JSON round trip without changing values", () => {
  const product = validateProduct({
    name: "Манометр",
    manufacturer: "Testo",
    specs: { погрешность: "±0,03 гПа (0 ... 0,30 гПа)" },
    description: "Назначение",
  });
  assert.deepEqual(parseProductJSON(JSON.stringify(product)), product);
});
