{
  const context = new AudioContext();
  const decoded = new Map();

  const load = async (cue) => {
    const response = await fetch(browser.runtime.getURL(`sounds/${cue}.wav`));
    decoded.set(cue, await context.decodeAudioData(await response.arrayBuffer()));
  };

  const play = (cue) => {
    const buffer = decoded.get(cue);
    if (!buffer) return;
    if (context.state === "suspended") context.resume();
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    source.start();
  };

  Object.values(KasualPad.Cue).forEach(load);
  browser.runtime.onMessage.addListener(({ cue }) => {
    if (cue) play(cue);
  });
}
