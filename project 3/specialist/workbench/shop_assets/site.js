"use strict";

function initReplyControls() {
  for (const image of document.querySelectorAll(".photo img")) {
    const hide = () => { image.hidden = true; };
    image.addEventListener("error", hide, { once: true });
    if (image.complete && image.naturalWidth === 0) hide();
  }
  const listen = document.querySelector("[data-listen]");
  if (!listen || !("speechSynthesis" in window)) return;

  const speech = window.speechSynthesis;
  const restore = () => { listen.textContent = "Read aloud"; };
  listen.hidden = false;
  listen.addEventListener("click", () => {
    if (speech.speaking) {
      speech.cancel();
      restore();
      return;
    }
    const utterance = new SpeechSynthesisUtterance(listen.closest("[data-spoken]").dataset.spoken);
    utterance.lang = "en";
    utterance.onend = restore;
    utterance.onerror = restore;
    listen.textContent = "Stop reading";
    speech.speak(utterance);
  });
}

function appendWaiting(main, message) {
  const thread = main.querySelector(".messages");
  if (!thread) return null;
  thread.querySelector("[data-transient]")?.remove();
  const wrapper = document.createElement("div");
  wrapper.className = "turn";
  wrapper.dataset.transient = "";
  const question = document.createElement("p");
  question.className = "user-message";
  question.setAttribute("aria-label", "You");
  question.textContent = message;
  const waiting = document.createElement("div");
  waiting.className = "assistant pending";
  waiting.setAttribute("role", "status");
  const mark = document.querySelector(".brand .mark").cloneNode(true);
  const answer = document.createElement("p");
  answer.className = "answer";
  answer.textContent = "Looking on Tunisianet…";
  waiting.append(mark, answer);
  wrapper.append(question, waiting);
  thread.append(wrapper);
  main.querySelector(".welcome")?.classList.add("is-chatting");
  wrapper.scrollIntoView({ block: "nearest" });
  return { wrapper, question, waiting, answer };
}

document.addEventListener("keydown", event => {
  if (!event.target.matches("[data-message]") || event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  event.target.form.requestSubmit();
});

document.addEventListener("submit", async event => {
  const form = event.target;
  const input = form.querySelector("[data-message]");
  if (!input || !window.fetch) return;

  event.preventDefault();
  const message = input.value.trim();
  if (!message || form.dataset.sending) return;
  form.dataset.sending = "true";
  const body = new URLSearchParams(new FormData(form));
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  input.readOnly = true;
  const current = document.getElementById("shopping-chat");
  const pending = appendWaiting(current, message);
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();

  try {
    const response = await fetch(form.getAttribute("action"), { method: "POST", body, credentials: "same-origin" });
    const parsed = new DOMParser().parseFromString(await response.text(), "text/html");
    const replacement = parsed.getElementById("shopping-chat");
    if (!replacement) throw new Error("No chat response");
    if (response.ok) {
      if (response.url !== location.href) history.pushState(null, "", response.url);
    } else {
      const retry = replacement.querySelector("[data-message]");
      if (retry) retry.value = message;
    }
    current.replaceWith(replacement);
    initReplyControls();
    const latest = replacement.querySelector("[data-latest]");
    if (latest) {
      latest.focus({ preventScroll: true });
      latest.scrollIntoView({ block: "nearest" });
    }
  } catch {
    if (pending) {
      pending.question.remove();
      pending.waiting.classList.remove("pending");
      pending.answer.textContent = "The search was interrupted. Try sending your message again.";
    }
    input.readOnly = false;
    button.disabled = false;
    delete form.dataset.sending;
    input.focus();
  }
});

window.addEventListener("popstate", () => window.location.reload());
initReplyControls();
