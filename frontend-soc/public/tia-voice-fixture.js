// Automated voice fixture for the disposable rig. Loaded when ?voice=fixture.
// It replaces the microphone and the speaker, not TIA: transcripts enter through the real
// recognition handlers, and spoken output is recorded instead of played on a physical speaker.
// It proves the browser control path. It does not prove microphone capture, echo, or barge-in.
(() => {
  try {
    const host = location.hostname;
    if (host !== "127.0.0.1" && host !== "localhost") return;
    if (new URLSearchParams(location.search).get("voice") !== "fixture") return;
  } catch (e) {
    return;
  }
  const fx = (window.__tiaFx = {
    events: [],
    recs: [],
    utterances: [],
    snapshot() {
      return {
        events: this.events.slice(),
        utterances: this.utterances.slice(),
        listening: this.recs.some((r) => r.live),
      };
    },
  });
  const log = (kind, data) => fx.events.push({ t: Math.round(performance.now()), kind, ...(data || {}) });

  class FakeRecognition {
    constructor() {
      this.continuous = false;
      this.interimResults = false;
      this.lang = "en-US";
      this.onresult = null;
      this.onerror = null;
      this.onend = null;
      this.live = false;
      fx.recs.push(this);
    }
    start() {
      this.live = true;
      log("mic_listening");
    }
    stop() {
      this.live = false;
      if (this.onend) this.onend();
    }
    abort() {
      if (this.live) log("mic_closed");
      this.live = false;
    }
  }
  window.SpeechRecognition = FakeRecognition;
  window.webkitSpeechRecognition = FakeRecognition;

  window.__say = (text) => {
    const rec = [...fx.recs].reverse().find((r) => r.live && r.onresult);
    if (!rec) {
      log("speech_not_heard", { text });
      return false;
    }
    log("operator_speech_end", { text });
    rec.onresult({
      resultIndex: 0,
      results: [Object.assign([{ transcript: text }], { isFinal: true, 0: { transcript: text } })],
    });
    return true;
  };

  if (navigator.mediaDevices) {
    navigator.mediaDevices.getUserMedia = async () => ({ getTracks: () => [] });
  }

  const voices = [{ name: "Fixture Voice", lang: "en-US", default: true, localService: true, voiceURI: "fixture" }];
  let current = [];
  const synth = {
    speaking: false,
    pending: false,
    paused: false,
    onvoiceschanged: null,
    getVoices: () => voices,
    resume() {},
    pause() {},
    cancel() {
      if (current.length) log("tts_cancelled", { remaining: current.length });
      const dropped = current;
      current = [];
      synth.speaking = false;
      dropped.forEach((u) => u.__timer && clearTimeout(u.__timer));
      dropped.forEach((u) => u.onerror && u.onerror({ error: "interrupted" }));
    },
    speak(u) {
      current.push(u);
      fx.utterances.push({ t: Math.round(performance.now()), text: u.text });
      log("tts_start", { text: u.text });
      synth.speaking = true;
      setTimeout(() => u.onstart && u.onstart({}), 10);
      u.__timer = setTimeout(() => {
        current = current.filter((x) => x !== u);
        synth.speaking = current.length > 0;
        log("tts_end", { text: u.text });
        if (u.onend) u.onend({});
      }, Math.min(2500, 40 * (u.text || "").length));
    },
  };
  Object.defineProperty(window, "speechSynthesis", { configurable: true, get: () => synth });

  const audioProto = window.HTMLAudioElement && window.HTMLAudioElement.prototype;
  if (audioProto) {
    const realPlay = audioProto.play;
    const realPause = audioProto.pause;
    audioProto.play = function play() {
      log("tts_audio_start", { src: String(this.src || "").slice(0, 48) });
      if (this.__tiaPlayTimer) clearTimeout(this.__tiaPlayTimer);
      this.__tiaPlayTimer = setTimeout(() => {
        this.__tiaPlayTimer = null;
        log("tts_audio_end");
        if (typeof this.onended === "function") this.onended();
      }, 2000);
      return Promise.resolve();
    };
    audioProto.pause = function pause() {
      if (this.__tiaPlayTimer) {
        clearTimeout(this.__tiaPlayTimer);
        this.__tiaPlayTimer = null;
        log("tts_audio_pause");
      }
      if (typeof realPause === "function") {
        try {
          realPause.call(this);
        } catch (e) {
          /* ignore */
        }
      }
    };
    audioProto.play.__tiaReal = realPlay;
  }

  const realFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    const watched = /soc-console\/(converse|ui-commands|speak|chat|telemetry)/.test(url);
    const started = performance.now();
    const res = await realFetch(input, init);
    if (watched) {
      let body = null;
      try {
        body = await res.clone().json();
      } catch (e) {
        body = null;
      }
      let sent = null;
      try {
        sent = init && init.body ? JSON.parse(init.body) : null;
      } catch (e) {
        sent = null;
      }
      log("http", {
        url: url.replace(/^https?:\/\/[^/]+/, ""),
        status: res.status,
        ms: Math.round(performance.now() - started),
        sent,
        body,
      });
    }
    return res;
  };
})();
