# OpenClaw Voice Bridge (Jarvis)

A lightweight voice interface for OpenClaw that lets you talk to your local AI through your browser.

Speech-to-text runs locally with Whisper and speech output is generated with Edge-TTS.

## Features

* Voice interaction with OpenClaw
* Browser interface
* Whisper speech recognition
* Text-to-speech responses
* No paid APIs required
* Simple two-terminal workflow

## Current Status

Experimental project tested on macOS.

## Requirements

* macOS
* Python 3.10+
* ffmpeg
* OpenClaw installed
* OpenClaw Gateway running

## Installation

Clone the repository:

```bash
git clone https://github.com/Al-iskander2/Jarvis.git
cd Jarvis
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install system dependency:

```bash
brew install ffmpeg
```

## Running the system

Start OpenClaw gateway first:

```bash
openclaw gateway start
```

Then start Jarvis in another terminal:

```bash
./start.sh
```

After startup the browser will open:

```
http://localhost:8000
```

Speak through the microphone to interact with OpenClaw.

## Notes

* Requires internet access for Edge-TTS
* Designed primarily for macOS
* Other platforms may work but are untested

## Roadmap

* Linux support
* Windows support
* Optional offline TTS
* Better install scripts

## License

MIT License
