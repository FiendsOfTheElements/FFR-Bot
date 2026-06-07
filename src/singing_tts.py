"""
singing_tts.py — Phoneme-based singing synthesizer for Discord bots

Strategy:
  1. Use eSpeak-NG to convert text → raw audio per syllable
  2. Pitch-shift each syllable to the target musical note
  3. Stitch segments together with crossfade overlap-add
  4. Add vibrato, Schroeder reverb, and a backing chord

Dependencies:
    pip install "discord.py[voice]" pydub scipy numpy anthropic
    sudo apt install espeak-ng ffmpeg   (Linux)
    brew install espeak-ng ffmpeg       (macOS)
"""

import io
import subprocess
import tempfile
import os
import json
import zlib
# import anthropic
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample, butter, lfilter
from pydub import AudioSegment
from pydub.effects import normalize

# ---------------------------------------------------------------------------
# Musical constants
# ---------------------------------------------------------------------------

def midi_to_hz(midi_note: int, cents: float = 0.0) -> float:
    return 440.0 * (2 ** ((midi_note - 69 + cents / 100.0) / 12))


def build_notes_dict(low_midi: int = 48, high_midi: int = 83) -> dict[str, int]:
    """Build note-name -> MIDI mapping, including enharmonic flat aliases."""
    names_sharp = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    sharp_to_flat = {
        "C#": "Db",
        "D#": "Eb",
        "F#": "Gb",
        "G#": "Ab",
        "A#": "Bb",
    }

    notes: dict[str, int] = {}
    for midi in range(low_midi, high_midi + 1):
        pitch_class = midi % 12
        octave = midi // 12 - 1
        sharp_name = f"{names_sharp[pitch_class]}{octave}"
        notes[sharp_name] = midi

        base_name = names_sharp[pitch_class]
        if base_name in sharp_to_flat:
            flat_name = f"{sharp_to_flat[base_name]}{octave}"
            notes[flat_name] = midi

    return notes


# Named notes C3-B5 (scientific pitch notation), including sharp/flat aliases.
NOTES = build_notes_dict()

# Small pitch offsets in cents by note class. This reduces rigid equal-tempered feel.
NOTE_CLASS_CENTS = {
    "C": 0.0,
    "D": 2.0,
    "E": -7.0,
    "F": -1.0,
    "G": 1.0,
    "A": -6.0,
    "B": -5.0,
}


def note_to_hz(note_name: str, syllable: str, phrase_index: int, phrase_len: int) -> float:
    """
    Convert note name to frequency with mild deterministic intonation variation.
    Keeps pitch centers stable while avoiding a robotic, over-quantized sound.
    """
    midi_note = NOTES.get(note_name, NOTES["C4"])

    note_class = note_name.rstrip("0123456789")
    if note_class.endswith("b"):
        note_class = note_class[0]
    if note_class.endswith("#"):
        note_class = note_class[0]

    class_cents = NOTE_CLASS_CENTS.get(note_class, 0.0)

    # Very small phrase contour: slight scoop early, settle later.
    if phrase_len <= 1:
        contour_cents = 0.0
    else:
        contour_cents = -2.0 + 4.0 * (phrase_index / (phrase_len - 1))

    # Deterministic micro-jitter in [-2.5, +2.5] cents per syllable-note position.
    seed = f"{syllable}|{note_name}|{phrase_index}".encode("utf-8")
    micro_cents = (zlib.crc32(seed) % 1001) / 1000.0 * 5.0 - 2.5

    return midi_to_hz(midi_note, cents=class_cents + contour_cents + micro_cents)

# Built-in melodies: list of (syllable, note_name, duration_seconds)
BUILTIN_MELODIES = {
    "twinkle": [
        ("Twinkle", "C4", 0.7), ("twinkle", "G4", 0.7),
        ("little",  "A4", 0.6), ("star", "G4", 0.70), ("", "REST", 0.3),
        ("How",  "F4", 0.35), ("I",    "F4", 0.35), ("won",  "E4", 0.35), ("der",  "E4", 0.35),
        ("what", "D4", 0.35), ("you",  "D4", 0.35), ("are",  "C4", 0.70),
    ],
    "happy_birthday": [
        ("Hap",  "C4", 0.30), ("py",    "C4", 0.15), ("birth", "D4", 0.45), ("day",  "C4", 0.45),
        ("to",   "F4", 0.45), ("you",   "C4", 0.90), ("", "REST", 0.5),
        ("Hap",  "C4", 0.30), ("py",    "C4", 0.15), ("birth", "D4", 0.45), ("day",  "C4", 0.45),
        ("to",   "G4", 0.45), ("you",   "C4", 0.90), ("", "REST", 0.5),
    ],
    "ode_to_joy": [
        ("Joy",  "E4", 0.4), ("ful", "E4", 0.4), ("joy",  "F4", 0.4), ("ful", "G4", 0.4),
        ("joy",  "G4", 0.4), ("ful", "F4", 0.4), ("joy",  "E4", 0.4), ("ful", "D4", 0.4),
        ("sing", "C4", 0.4), ("ing", "C4", 0.4), ("songs", "D4", 0.4), ("of",  "E4", 0.4),
        ("praise","E4", 0.6), ("to", "D4", 0.2), ("you",  "D4", 0.8),
    ],
    "warmech": [
        ("You", "D4", 0.25), ("strolled", "E4", 0.4), ("in", "D4", 0.2), ("to", "C4", 0.25), 
        ("my", "D4", 0.2), ("sky", "F4", 0.45), ("bridge", "E4", 0.45), ("look", "D4", 0.25), 
        ("ing", "C4", 0.2), ("for", "C4", 0.2), ("a", "D4", 0.2), ("final", "E4", 0.35), 
        ("fan", "E4", 0.35), ("ta", "D4", 0.2), ("sy", "C4", 0.3), 
        ("but", "D4", 0.25), ("found", "E4", 0.4), ("me", "G4", 0.5), ("in", "F4", 0.25), 
        ("stead", "E4", 0.45), ("I", "D4", 0.25), ("am", "C4", 0.2), ("the", "C4", 0.2), 
        ("War", "E4", 0.5), ("mech", "G4", 0.6), ("a", "F4", 0.25), ("rare", "E4", 0.4), 
        ("sur", "D4", 0.25), ("prise", "C4", 0.4), ("your", "D4", 0.25), ("chan", "E4", 0.35), 
        ("ces", "D4", 0.2), ("of", "C4", 0.2), ("sur", "E4", 0.4), ("vi", "F4", 0.3), 
        ("val", "E4", 0.35), ("are", "D4", 0.2), ("ze", "G4", 0.5), ("ro", "E4", 0.45), 
        ("per", "D4", 0.25), ("cent", "C4", 0.4), ("nu", "E4", 0.45), ("cle", "F4", 0.3), 
        ("ar", "G4", 0.5), ("waste", "F4", 0.4), ("is", "E4", 0.25), ("so", "D4", 0.25), 
        ("clean", "C4", 0.5), ("for", "D4", 0.25), ("sci", "E4", 0.4), ("ence", "D4", 0.35), 
        ("you", "C4", 0.25), ("will", "D4", 0.25), ("now", "E4", 0.4), ("be", "F4", 0.25),
        ("deleted", "G4", 0.9),
    ],
}

# ---------------------------------------------------------------------------
# eSpeak-NG wrapper
# ---------------------------------------------------------------------------

# GLaDOS-like baseline: calm female timbre, flatter pitch bias, less shouty amplitude.
ESPEAK_VOICE = "en-us+f3"
ESPEAK_SPEED = 130
ESPEAK_PITCH = 42
ESPEAK_AMPLITUDE = 165
DEFAULT_TEMPO_SCALE = 1.18
DEFAULT_WORD_GAP_S = 0.0
REST_NOTE_NAMES = {"REST", "R", "PAUSE", "SIL"}


def is_rest_note(note_name: str) -> bool:
    """Return True if this note indicates an intentional silent rest."""
    return note_name.strip().upper() in REST_NOTE_NAMES

def espeak_synthesize(text: str, sample_rate: int = 22050) -> np.ndarray:
    """
    Synthesize a syllable/word with eSpeak-NG.
    Returns a float32 numpy array (mono, normalized to [-1, 1]).
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        subprocess.run(
            [
                "espeak-ng",
                "-v", ESPEAK_VOICE,
                "-s", str(ESPEAK_SPEED),
                "-p", str(ESPEAK_PITCH),
                "-a", str(ESPEAK_AMPLITUDE),
                "-w", tmp_path,  # output WAV
                text,
            ],
            check=True,
            capture_output=True,
        )
        sr, data = wavfile.read(tmp_path)

        if data.ndim > 1:
            data = data.mean(axis=1)
        audio = data.astype(np.float32) / np.iinfo(data.dtype).max

        if sr != sample_rate:
            target_len = int(len(audio) * sample_rate / sr)
            audio = resample(audio, target_len)

        return audio
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ---------------------------------------------------------------------------
# Pitch shifting
# ---------------------------------------------------------------------------

def estimate_fundamental(audio: np.ndarray, sample_rate: int) -> float:
    """Autocorrelation-based F0 estimation. Returns Hz or 150.0 on failure."""
    if len(audio) < sample_rate // 10:
        return 150.0

    frame_len = min(2048, len(audio))
    start = max(0, len(audio) // 2 - frame_len // 2)
    frame = audio[start : start + frame_len]
    frame = frame - frame.mean()

    corr = np.correlate(frame, frame, mode="full")
    corr = corr[len(corr) // 2:]

    min_lag = int(sample_rate / 400)
    max_lag = int(sample_rate / 80)
    if max_lag >= len(corr):
        return 150.0

    peak = np.argmax(corr[min_lag:max_lag]) + min_lag
    return sample_rate / peak if peak > 0 else 150.0


def pitch_shift_resample(
    audio: np.ndarray,
    source_hz: float,
    target_hz: float,
    target_duration_samples: int,
) -> np.ndarray:
    """
    Pitch-shift by resampling (changes pitch + speed), then
    time-stretch back to the desired note duration.
    """
    if source_hz <= 0:
        source_hz = 150.0

    ratio = source_hz / target_hz
    new_len = max(1, int(len(audio) * ratio))
    pitch_shifted = resample(audio, new_len)

    if len(pitch_shifted) == 0:
        return np.zeros(target_duration_samples, dtype=np.float32)

    return resample(pitch_shifted, target_duration_samples).astype(np.float32)


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------

def apply_note_envelope(
    audio: np.ndarray,
    sample_rate: int,
    attack_ms: float = 12.0,
    release_ms: float = 35.0,
) -> np.ndarray:
    """Apply short attack/release so syllables connect more naturally."""
    n = len(audio)
    if n == 0:
        return audio

    attack = max(1, int(sample_rate * attack_ms / 1000.0))
    release = max(1, int(sample_rate * release_ms / 1000.0))
    attack = min(attack, n)
    release = min(release, n)

    env = np.ones(n, dtype=np.float32)
    env[:attack] *= np.linspace(0.0, 1.0, attack, dtype=np.float32)
    env[-release:] *= np.linspace(1.0, 0.0, release, dtype=np.float32)
    return (audio * env).astype(np.float32)


def apply_glados_tone(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Tone-shape to a smoother synthetic-female profile and tame harshness."""
    if len(audio) < 8:
        return audio

    nyquist = sample_rate / 2.0
    hp_cut = min(120.0, nyquist * 0.9)
    lp_cut = min(3400.0, nyquist * 0.95)

    hp_b, hp_a = butter(2, hp_cut / nyquist, btype="high")
    lp_b, lp_a = butter(2, lp_cut / nyquist, btype="low")

    shaped = lfilter(hp_b, hp_a, audio)
    shaped = lfilter(lp_b, lp_a, shaped)

    # Gentle soft saturation for cohesion without obvious distortion.
    shaped = np.tanh(shaped * 1.25) / np.tanh(1.25)
    return shaped.astype(np.float32)

def add_vibrato(
    audio: np.ndarray,
    sample_rate: int,
    rate_hz: float = 4.6,
    depth: float = 0.004,
    delay_s: float = 0.2,
) -> np.ndarray:
    """Sinusoidal index modulation vibrato, fades in after delay_s."""
    n = len(audio)
    t = np.arange(n) / sample_rate
    delay_samples = int(delay_s * sample_rate)

    envelope = np.zeros(n)
    if delay_samples < n:
        fade_len = min(int(0.05 * sample_rate), n - delay_samples)
        envelope[delay_samples : delay_samples + fade_len] = np.linspace(0, 1, fade_len)
        if delay_samples + fade_len < n:
            envelope[delay_samples + fade_len :] = 1.0

    vibrato = 1.0 + depth * envelope * np.sin(2 * np.pi * rate_hz * t)
    indices = np.cumsum(vibrato)
    indices = indices / indices[-1] * (n - 1)
    indices = np.clip(indices, 0, n - 1)

    idx_floor = indices.astype(int)
    idx_ceil  = np.minimum(idx_floor + 1, n - 1)
    frac      = indices - idx_floor
    return (audio[idx_floor] * (1 - frac) + audio[idx_ceil] * frac).astype(np.float32)


def add_reverb(audio: np.ndarray, sample_rate: int, room_scale: float = 0.3) -> np.ndarray:
    """Schroeder reverb: four parallel comb filters."""
    delays_ms = [29.7, 37.1, 41.1, 43.7]
    gains     = [0.805, 0.827, 0.783, 0.764]
    out = audio.copy()
    for delay_ms, gain in zip(delays_ms, gains):
        delay_samples = int(delay_ms * room_scale * sample_rate / 1000)
        if delay_samples <= 0 or delay_samples >= len(audio):
            continue
        comb = np.zeros_like(audio)
        comb[delay_samples:] = audio[: len(audio) - delay_samples] * gain
        out = out + comb * 0.25
    peak = np.max(np.abs(out))
    if peak > 0:
        out = out / peak * 0.9
    return out.astype(np.float32)


def generate_chord(
    notes_hz: list[float],
    duration_samples: int,
    sample_rate: int,
    amplitude: float = 0.05,
) -> np.ndarray:
    """Soft sine-wave pad chord with slight detune for warmth."""
    t = np.arange(duration_samples) / sample_rate
    chord = np.zeros(duration_samples, dtype=np.float32)
    for hz in notes_hz:
        chord += np.sin(2 * np.pi * hz * t) * amplitude
        chord += np.sin(2 * np.pi * hz * 1.003 * t) * amplitude * 0.5
    fade = int(0.05 * sample_rate)
    if fade < duration_samples:
        chord[:fade]  *= np.linspace(0, 1, fade)
        chord[-fade:] *= np.linspace(1, 0, fade)
    return chord


# C-major backing chord
C_MAJOR_HZ = [midi_to_hz(NOTES[n]) for n in ("C3", "E3", "G3")]


# ---------------------------------------------------------------------------
# Main synthesizer
# ---------------------------------------------------------------------------

def synthesize_song(
    melody: list[tuple[str, str, float]],
    sample_rate: int = 22050,
    vibrato: bool = True,
    reverb: bool = True,
    backing_chord: bool = True,
    crossfade_ms: int = 45,
    tempo_scale: float = DEFAULT_TEMPO_SCALE,
    word_gap_s: float = DEFAULT_WORD_GAP_S,
) -> AudioSegment:
    """
    Synthesize a melody into a pydub AudioSegment.

    Args:
        melody:        List of (syllable, note_name, duration_seconds).
        sample_rate:   Audio sample rate.
        vibrato:       Add vibrato on notes longer than 0.3s.
        reverb:        Add Schroeder room reverb.
        backing_chord: Mix in a soft C-major pad.
        crossfade_ms:  Overlap-add crossfade between syllables.
        tempo_scale:   Global speed control. >1.0 slows the song down.
        word_gap_s:    Extra fixed silence added at each non-crossfaded join.
                   Use REST notes in melody for explicit composer pauses.

    Returns:
        pydub AudioSegment (mono, normalized).
    """
    if not melody:
        return AudioSegment.silent(duration=1000)

    segments = []
    segment_is_rest = []
    crossfade_samples = int(crossfade_ms * sample_rate / 1000)
    word_gap_samples = int(max(0.0, word_gap_s) * sample_rate)

    note_is_rest = [is_rest_note(note_name) for _, note_name, _ in melody]
    join_has_crossfade = [
        (not note_is_rest[i]) and (not note_is_rest[i + 1])
        for i in range(len(melody) - 1)
    ]

    for idx, (syllable, note_name, duration_s) in enumerate(melody):
        scaled_duration_s = max(0.1, duration_s * tempo_scale)

        # Overlap-add removes crossfade samples on each join; compensate here
        # so the audible timeline is closer to intended musical duration.
        overlap_comp_samples = 0
        if idx < len(melody) - 1 and join_has_crossfade[idx]:
            overlap_comp_samples = crossfade_samples
        target_samples = int(scaled_duration_s * sample_rate) + overlap_comp_samples

        if note_is_rest[idx]:
            segments.append(np.zeros(target_samples, dtype=np.float32))
            segment_is_rest.append(True)
            continue

        target_hz = note_to_hz(note_name, syllable, idx, len(melody))

        raw = espeak_synthesize(syllable, sample_rate)

        # Trim leading/trailing silence
        threshold = 0.01
        nonzero = np.where(np.abs(raw) > threshold)[0]
        if len(nonzero) > 10:
            raw = raw[nonzero[0] : nonzero[-1] + 1]
        if len(raw) < 10:
            raw = np.zeros(target_samples, dtype=np.float32)

        source_hz = estimate_fundamental(raw, sample_rate)
        sung      = pitch_shift_resample(raw, source_hz, target_hz, target_samples)

        if vibrato and scaled_duration_s > 0.3:
            sung = add_vibrato(sung, sample_rate)

        sung = apply_note_envelope(sung, sample_rate)

        segments.append(sung)
        segment_is_rest.append(False)

    # Overlap-add stitch
    stitched = segments[0].copy()
    for i, seg in enumerate(segments[1:], start=1):
        if not join_has_crossfade[i - 1]:
            if word_gap_samples > 0 and not (segment_is_rest[i - 1] or segment_is_rest[i]):
                stitched = np.concatenate([stitched, np.zeros(word_gap_samples, dtype=np.float32), seg])
            else:
                stitched = np.concatenate([stitched, seg])
            continue

        if len(stitched) > crossfade_samples and len(seg) > crossfade_samples:
            fade_out = np.linspace(1, 0, crossfade_samples)
            fade_in  = np.linspace(0, 1, crossfade_samples)
            stitched[-crossfade_samples:] = (
                stitched[-crossfade_samples:] * fade_out
                + seg[:crossfade_samples] * fade_in
            )
            stitched = np.concatenate([stitched, seg[crossfade_samples:]])
        else:
            stitched = np.concatenate([stitched, seg])

    if backing_chord:
        chord    = generate_chord(C_MAJOR_HZ, len(stitched), sample_rate)
        stitched = stitched * 0.85 + chord

    stitched = apply_glados_tone(stitched, sample_rate)

    if reverb:
        stitched = add_reverb(stitched, sample_rate, room_scale=0.2)

    peak = np.max(np.abs(stitched))
    if peak > 0:
        stitched = stitched / peak * 0.92

    pcm_16 = (stitched * 32767).astype(np.int16)
    return normalize(AudioSegment(
        pcm_16.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1,
    ))


def song_to_bytes(audio_seg: AudioSegment, fmt: str = "mp3") -> bytes:
    """Export an AudioSegment to bytes."""
    buf = io.BytesIO()
    audio_seg.export(buf, format=fmt)
    buf.seek(0)
    return buf.read()
