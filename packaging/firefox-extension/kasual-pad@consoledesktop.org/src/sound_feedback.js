KasualPad.SoundFeedback = class {
  play(cue) {
    browser.runtime.sendMessage({ cue });
  }
};
