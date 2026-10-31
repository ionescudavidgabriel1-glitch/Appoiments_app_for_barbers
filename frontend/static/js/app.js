// Small interactions that make the pages respond to the person using them.
// Every page works without this file; it only adds feedback.

// Flash messages: close button, and fade out on their own after a few seconds.
function dismissFlash(flash) {
  flash.classList.add("is-leaving");
  flash.addEventListener("transitionend", () => flash.remove(), { once: true });
}

document.querySelectorAll(".flash").forEach((flash) => {
  flash.querySelector("[data-dismiss]")?.addEventListener("click", () => dismissFlash(flash));
  if (flash.dataset.autohide !== undefined) {
    setTimeout(() => dismissFlash(flash), 6000);
  }
});

// Submit buttons: show a spinner and a "working" label so a click never feels ignored.
document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", () => {
    const button = form.querySelector("button[data-loading-text]");
    if (!button) return;
    button.setAttribute("aria-busy", "true");
    button.textContent = button.dataset.loadingText;
  });
});

// Password fields: a Show / Hide toggle.
document.querySelectorAll("[data-toggle-password]").forEach((toggle) => {
  const input = document.getElementById(toggle.dataset.togglePassword);
  toggle.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    toggle.textContent = show ? "Hide" : "Show";
    toggle.setAttribute("aria-pressed", String(show));
  });
});

// Greeting by the visitor's own time of day.
document.querySelectorAll("[data-greet]").forEach((el) => {
  const hour = new Date().getHours();
  const part = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  el.textContent = `${part}, ${el.dataset.greet}`;
});

// Home page demo: click a free slot to book it, click again to free it.
document.querySelectorAll("[data-demo-slot]").forEach((slot) => {
  const freeLabel = slot.innerHTML;
  slot.addEventListener("click", () => {
    const booking = !slot.classList.contains("slot-mine");
    slot.classList.toggle("slot-mine", booking);
    slot.setAttribute("aria-pressed", String(booking));
    slot.innerHTML = booking
      ? '<span>You · Haircut</span><span class="stamp">Booked</span>'
      : freeLabel;
  });
});

// Copy buttons: data-copy="input-id" copies that input's value.
document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const input = document.getElementById(button.dataset.copy);
    try {
      await navigator.clipboard.writeText(input.value);
    } catch {
      input.select();
      document.execCommand("copy");
    }
    const label = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => (button.textContent = label), 2000);
  });
});

// Working hours: copy Monday's times to Tuesday through Friday.
document.querySelectorAll("[data-copy-monday]").forEach((button) => {
  const form = button.closest("form");
  button.addEventListener("click", () => {
    const monday = [...form.querySelectorAll('[data-day="0"] input[type="time"]')];
    for (let day = 1; day <= 4; day++) {
      form.querySelectorAll(`[data-day="${day}"] input[type="time"]`).forEach((input, i) => {
        input.value = monday[i].value;
      });
    }
    button.textContent = "Copied to Tuesday–Friday";
  });
});
