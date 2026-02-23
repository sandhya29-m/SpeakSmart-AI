const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const speechText = document.getElementById("speechText");
const correctedText = document.getElementById("correctedText");

let recognition;
let mediaRecorder;
let audioChunks = [];

// ✅ Speech Recognition
window.SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (window.SpeechRecognition) {
  recognition = new window.SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onresult = async (event) => {
    let transcript = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }
    speechText.textContent = transcript;

    if (transcript.trim().length > 0) {
      try {
        const response = await fetch("/correct", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: transcript })
        });
        const data = await response.json();
        correctedText.textContent = "✅ " + data.corrected;
      } catch (error) {
        correctedText.textContent = "⚠️ Grammar check error.";
      }
    }
  };

  startBtn.onclick = async () => {
    recognition.start();

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks, { type: "audio/wav" });
      const formData = new FormData();
      formData.append("audio", blob, "speech.wav");

      try {
        const response = await fetch("/emotion", { method: "POST", body: formData });
        const data = await response.json();
        correctedText.textContent += "\n🧠 Confidence Analysis: " + data.emotion;
      } catch (err) {
        correctedText.textContent += "\n⚠️ Emotion detection failed.";
      }

      audioChunks = [];
    };

    mediaRecorder.start();
  };

  stopBtn.onclick = () => {
    recognition.stop();
    mediaRecorder.stop();
  };

} else {
  alert("❌ Speech Recognition not supported in this browser. Use Chrome.");
}
