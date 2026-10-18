const board = document.querySelector("#board");
const nav = document.querySelector("#chars");
const summary = document.querySelector("#summary");
const showLine = document.querySelector("#show-line");

let data = null;
let current = "永";

function turnsText(stroke) {
  if (!stroke.turns.length) {
    const seg = stroke.segments[0];
    return seg ? `1 段，走向 ${seg.angle}°` : "1 段";
  }
  const angles = stroke.turns.map((t) => `${t}°`).join("、");
  return `${stroke.segments.length} 段，转角 ${angles}`;
}

function frame(character, step) {
  const paths = character.strokes
    .map((stroke, index) => {
      let fill = "#d4d0c8";
      if (index < step) fill = "#1c1c1c";
      if (index === step) fill = "#c41616";
      return `<path d="${stroke.svg}" fill="${fill}"/>`;
    })
    .join("");
  let line = "";
  if (showLine.checked) {
    const pts = character.strokes[step].centerline.map((p) => p.join(",")).join(" ");
    line = `<polyline points="${pts}" fill="none" stroke="#1f4e79" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;
  }
  return `<svg viewBox="0 0 256 256" role="img" aria-label="第 ${step + 1} 笔">${paths ? `<g transform="translate(0 220) scale(1 -1)">${paths}${line}</g>` : ""}</svg>`;
}

function render() {
  const character = data.characters.find((item) => item.char === current);
  nav.querySelectorAll("button").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.char === current ? "true" : "false");
  });
  if (!character?.ok) {
    summary.textContent = character?.reason || "没有这个字的数据";
    board.innerHTML = "";
    return;
  }
  const byCodes = character.orderMethod !== "animation";
  const how = byCodes
    ? "按笔画类别对齐总表。"
    : "类别对不上总表，笔序改由笔顺动画的分笔图确定。";
  summary.textContent = `${character.char} · ${character.strokes.length} 画 · 笔顺 ${character.codes} · ${character.radical}部。${how}`;
  board.innerHTML = character.strokes
    .map(
      (stroke, index) => `<article>
        <h2>第 ${stroke.step} 笔 · ${stroke.name}</h2>
        <p>编号 ${stroke.code}（${stroke.codeLabel}）。${turnsText(stroke)}</p>
        ${frame(character, index)}
      </article>`
    )
    .join("");
}

function select(char) {
  current = char;
  render();
}

fetch("data/strokes.json")
  .then((res) => {
    if (!res.ok) throw new Error(`无法读取笔画数据（${res.status}）`);
    return res.json();
  })
  .then((payload) => {
    data = payload;
    nav.innerHTML = data.characters
      .map(
        (item) =>
          `<button type="button" data-char="${item.char}" aria-pressed="false">${item.char}</button>`
      )
      .join("");
    nav.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (button) select(button.dataset.char);
    });
    showLine.addEventListener("change", render);
    select("永");
  })
  .catch((error) => {
    summary.textContent = `${error.message}。请在 web 目录运行 python -m http.server。`;
  });
