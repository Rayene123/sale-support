"use strict";

let running = null;

function initReplyControls() {
  for (const image of document.querySelectorAll(".photo img")) {
    const hide = () => {
      image.closest(".photo").hidden = true;
      image.closest(".product").classList.remove("with-photo");
    };
    image.addEventListener("error", hide, { once: true });
    if (image.complete && !image.naturalWidth) hide();
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

function resetControls(request) {
  if (request.input) request.input.readOnly = false;
  if (request.button) request.button.disabled = false;
  if (request.stop) request.stop.hidden = true;
  request.form.removeAttribute("aria-busy");
}

function updateViewport() {
  const viewport = window.visualViewport;
  const inset = viewport && viewport.scale === 1 ? Math.max(0, innerHeight - viewport.height - viewport.offsetTop) : 0;
  document.documentElement.style.setProperty("--keyboard-inset", Math.round(inset) + "px");
}

document.addEventListener("keydown", event => {
  if (!event.target.matches("[data-message]") || event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  event.target.form.requestSubmit();
});

document.addEventListener("click", event => {
  const stop = event.target.closest("[data-stop]");
  if (stop && running) {
    const request = running;
    running = null;
    request.controller.abort();
    void fetch("/shop/stop/", {
      method: "POST", credentials: "same-origin", keepalive: true,
      body: new URLSearchParams({ csrf: request.csrf, operation: request.operation }),
    }).catch(() => {});
    request.pending?.question.remove();
    request.pending?.waiting.classList.remove("pending");
    if (request.pending) request.pending.answer.textContent = "Search stopped.";
    resetControls(request);
    request.input?.focus({ preventScroll: true });
    return;
  }
  const example = event.target.closest("[data-suggest]");
  if (example && !running) {
    const input = document.querySelector("[data-message]");
    if (input) {
      input.value = example.dataset.suggest;
      input.form.requestSubmit();
    }
  }
  const photo = event.target.closest("[data-photo]");
  if (photo) {
    const dialog = document.querySelector(".photo-dialog");
    const image = dialog.querySelector("img");
    image.src = photo.dataset.photo;
    image.alt = photo.dataset.name;
    dialog.showModal();
  }
});

document.addEventListener("submit", async event => {
  const form = event.target;
  const input = form.querySelector("[data-message]");
  if (form.querySelector('[name="action"]')?.value === "refresh") {
    const button = form.querySelector("button");
    button.textContent = "Checking…";
    button.disabled = true;
  }
  if (!input || !window.fetch || !crypto.randomUUID) return;

  event.preventDefault();
  const message = input.value.trim();
  if (!message || running) return;
  const body = new URLSearchParams(new FormData(form));
  const operation = crypto.randomUUID();
  const controller = new AbortController();
  body.set("operation", operation);
  const button = form.querySelector("button[type=submit]");
  const stop = form.querySelector("[data-stop]");
  const current = document.getElementById("shopping-chat");

  input.value = "";
  input.readOnly = true;
  button.disabled = true;
  stop.hidden = false;
  form.setAttribute("aria-busy", "true");
  const pending = appendWaiting(current, message);
  const request = { controller, operation, csrf: body.get("csrf"), form, input, button, stop, pending };
  running = request;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();

  try {
    const response = await fetch(form.getAttribute("action"), {
      method: "POST", body, credentials: "same-origin", signal: controller.signal,
    });
    const parsed = new DOMParser().parseFromString(await response.text(), "text/html");
    if (running !== request) return;
    const replacement = parsed.getElementById("shopping-chat");
    if (!replacement) throw new Error("No chat response");
    if (response.ok) {
      if (response.url !== location.href) history.pushState(null, "", response.url);
    } else {
      const retry = replacement.querySelector("[data-message]");
      if (retry) retry.value = message;
    }
    current.replaceWith(replacement);
    const header = parsed.getElementById("shop-header");
    if (header) document.getElementById("shop-header").replaceWith(header);
    initReplyControls();
    const latest = replacement.querySelector("[data-latest]");
    if (latest) {
      latest.classList.add("arriving");
      latest.focus({ preventScroll: true });
      latest.scrollIntoView({ block: "nearest" });
    }
  } catch {
    if (running !== request) return;
    if (pending) {
      pending.question.remove();
      pending.waiting.classList.remove("pending");
      pending.answer.textContent = "The search was interrupted. Try sending your message again.";
    }
    input.value = message;
    input.focus();
  } finally {
    if (running === request) {
      running = null;
      resetControls(request);
    }
  }
});

window.addEventListener("popstate", () => window.location.reload());
window.visualViewport?.addEventListener("resize", updateViewport);
window.visualViewport?.addEventListener("scroll", updateViewport);
initReplyControls();
