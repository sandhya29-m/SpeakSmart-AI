let recognition;
let recognizing = false;

if (!("webkitSpeechRecognition" in window)) {
    alert("Your browser does not support Speech Recognition.");
} else {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = function(event) {
        let interim_transcript = "";
        let final_transcript = "";

        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                final_transcript += event.results[i][0].transcript;
            } else {
                interim_transcript += event.results[i][0].transcript;
            }
        }

        let display_text = final_transcript || interim_transcript;
        document.getElementById("original").innerText = display_text;

        // Send to backend live
        fetch("/process_text", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: display_text })
        })
        .then(res => res.json())
        .then(data => {
            document.getElementById("corrected").innerHTML = data.highlighted;
            document.getElementById("confidence").innerText = data.confidence;
        });
    };
}

document.getElementById("startBtn").onclick = () => {
    if (!recognizing) {
        recognition.start();
        recognizing = true;
    }
};

document.getElementById("stopBtn").onclick = () => {
    if (recognizing) {
        recognition.stop();
        recognizing = false;
    }
};
