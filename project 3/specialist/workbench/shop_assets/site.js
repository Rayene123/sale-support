"use strict";

const requestInput = document.querySelector("#request");
for (const button of document.querySelectorAll("[data-example]")) {
  button.addEventListener("click", () => {
    requestInput.value = button.dataset.example;
    requestInput.focus();
  });
}

for (const button of document.querySelectorAll("[data-search]")) {
  const form = button.form;
  const progress = form.querySelector(".search-progress");
  form.addEventListener("submit", () => {
    button.disabled = true;
    form.setAttribute("aria-busy", "true");
    if (progress) progress.hidden = false;
  });
  window.addEventListener("pageshow", () => {
    button.disabled = false;
    form.removeAttribute("aria-busy");
    if (progress) progress.hidden = true;
  });
}

for (const image of document.querySelectorAll(".product-image img")) {
  const showFallback = () => {
    image.hidden = true;
    image.parentElement.querySelector(".photo-fallback").hidden = false;
  };
  image.addEventListener("error", showFallback, { once: true });
  if (image.complete && image.naturalWidth === 0) showFallback();
}

const listen = document.querySelector("[data-listen]");
if (listen && "speechSynthesis" in window) {
  const speech = window.speechSynthesis;
  const restore = () => { listen.textContent = "Listen"; };
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
