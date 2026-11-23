{
  const TEXT_INPUT_SELECTOR = [
    "input:not([type])",
    'input[type="text"]',
    'input[type="search"]',
    'input[type="email"]',
    'input[type="password"]',
    'input[type="tel"]',
    'input[type="url"]',
    "textarea",
  ].join(",");

  KasualPad.isTextInput = (element) => element?.matches?.(TEXT_INPUT_SELECTOR) === true;

  KasualPad.replaceText = (input, text) => {
    input.value = text;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  };

  KasualPad.waitFor = (find, timeoutMs) => new Promise((resolve) => {
    const deadline = performance.now() + timeoutMs;
    const poll = () => {
      const found = find();
      if (found || performance.now() >= deadline) resolve(found ?? null);
      else requestAnimationFrame(poll);
    };
    poll();
  });
}
