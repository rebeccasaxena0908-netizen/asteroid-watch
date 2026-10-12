// Small UI effects: count-up numbers, scroll reveals, card glow, error banner.

export const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

const easeOutExpo = (t) => (t === 1 ? 1 : 1 - 2 ** (-10 * t));

/** Animate an element's number from 0 to `value`. format(n) turns the number into text. */
export function countUp(node, value, format, duration = 1400) {
  if (value == null || Number.isNaN(value)) {
    node.textContent = '–';
    return;
  }
  if (reducedMotion.matches) {
    node.textContent = format(value);
    return;
  }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / duration);
    node.textContent = format(value * easeOutExpo(t));
    if (t < 1) requestAnimationFrame(step);
    else node.textContent = format(value);
  };
  requestAnimationFrame(step);
}

/** Fade/slide elements with .reveal in when they scroll into view (staggered by --i). */
export function setupReveal() {
  const nodes = document.querySelectorAll('.reveal');
  if (reducedMotion.matches || !('IntersectionObserver' in window)) {
    nodes.forEach((n) => n.classList.add('in'));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        io.unobserve(e.target);
      }
    }
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
  nodes.forEach((n) => io.observe(n));
}

/** A soft light on each card that follows the pointer. */
export function setupCardGlow() {
  for (const card of document.querySelectorAll('.card')) {
    card.addEventListener('pointermove', (e) => {
      const r = card.getBoundingClientRect();
      card.style.setProperty('--mx', `${e.clientX - r.left}px`);
      card.style.setProperty('--my', `${e.clientY - r.top}px`);
    });
  }
}

let retryHandler = null;
export function showBanner(message, onRetry) {
  document.getElementById('banner-msg').textContent = message;
  retryHandler = onRetry;
  document.getElementById('banner').hidden = false;
}
export function hideBanner() {
  document.getElementById('banner').hidden = true;
}
document.getElementById('banner-retry')?.addEventListener('click', () => {
  hideBanner();
  retryHandler?.();
});
