{
  const INTERACTIVE_SELECTOR = [
    "a[href]",
    "button",
    "input",
    "select",
    "textarea",
    '[role="button"]',
    '[role="link"]',
    '[role="tab"]',
    '[role="menuitem"]',
    '[tabindex]:not([tabindex="-1"])',
  ].join(",");

  const MODAL_SELECTOR = '[role="dialog"], [aria-modal="true"]';
  const HIDDEN_FROM_USERS = '[aria-hidden="true"]';

  const hasArea = (rect) => rect.width > 0 && rect.height > 0;

  const isReachable = (element) => {
    const rect = element.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerWithinViewportWidth = centerX >= 0 && centerX <= innerWidth;
    return hasArea(rect)
      && centerWithinViewportWidth
      && !element.disabled
      && !element.closest(HIDDEN_FROM_USERS)
      && getComputedStyle(element).visibility !== "hidden";
  };

  const innermostOnly = (elements) =>
    elements.filter((element) => !elements.some((other) => other !== element && element.contains(other)));

  KasualPad.isReachable = isReachable;

  KasualPad.interactiveElementsIn = (scope) =>
    innermostOnly(Array.from(scope.querySelectorAll(INTERACTIVE_SELECTOR)).filter(isReachable));

  KasualPad.topmostModal = () =>
    Array.from(document.querySelectorAll(MODAL_SELECTOR))
      .filter((modal) => hasArea(modal.getBoundingClientRect()))
      .at(-1) ?? null;
}
