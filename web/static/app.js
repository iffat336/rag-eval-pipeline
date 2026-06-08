const EXAMPLE_QUESTIONS = [
  "What header is used to authenticate API requests, and how do live and test keys differ?",
  "How does OAuth token refresh work, and how is that different from how service accounts authenticate?",
  "If my webhook endpoint goes down, how does Nimbus handle retrying delivery?",
  "I'm on the Starter plan and going over my quota — what happens, and can I get a higher rate limit?",
];

const form = document.getElementById("ask-form");
const input = document.getElementById("question-input");
const button = document.getElementById("ask-button");
const status = document.getElementById("status");
const results = document.getElementById("results");
const chipsContainer = document.getElementById("example-chips");

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderExampleChips() {
  for (const question of EXAMPLE_QUESTIONS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = question;
    chip.addEventListener("click", () => {
      input.value = question;
      form.requestSubmit();
    });
    chipsContainer.appendChild(chip);
  }
}

function renderResult(result) {
  const card = document.createElement("article");
  card.className = "result";

  let subQuestionsHtml = "";
  if (result.sub_questions && result.sub_questions.length > 1) {
    const items = result.sub_questions.map((q) => `<li>${escapeHtml(q)}</li>`).join("");
    subQuestionsHtml = `
      <span class="label">Decomposed into sub-questions</span>
      <ul class="sub-questions">${items}</ul>
    `;
  }

  const contextItems = (result.contexts || [])
    .map(
      (ctx) => `
        <div class="context-item">
          <div class="context-source">${escapeHtml(ctx.source)}</div>
          <div class="context-text">${escapeHtml(ctx.text)}</div>
        </div>`
    )
    .join("");

  card.innerHTML = `
    <h3>❓ ${escapeHtml(result.question)}</h3>
    ${subQuestionsHtml}
    <span class="label">Answer</span>
    <div class="answer">${escapeHtml(result.answer)}</div>
    <details class="contexts">
      <summary>Retrieved context (${(result.contexts || []).length} passages)</summary>
      ${contextItems}
    </details>
  `;

  results.prepend(card);
}

async function handleSubmit(event) {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;

  button.disabled = true;
  status.textContent = "Decomposing → retrieving → reranking → generating…";
  status.classList.remove("error");

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Something went wrong.");
    }

    renderResult(data);
    status.textContent = `${data.remaining_today} question(s) remaining for you today.`;
    input.value = "";
  } catch (err) {
    status.textContent = err.message || "Something went wrong. Please try again.";
    status.classList.add("error");
  } finally {
    button.disabled = false;
  }
}

renderExampleChips();
form.addEventListener("submit", handleSubmit);
