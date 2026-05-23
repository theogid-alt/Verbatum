from __future__ import annotations

import asyncio
import re
import time
from typing import AsyncIterator

from verbatim.instrumentation.recorder import CallRecorder


WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?")
PUNCTUATION_RE = re.compile(r"[.!?](?:\s|$)")


class FirstPhraseTextAggregator:
    """Hybrid first-phrase aggregator for low-latency voice starts.

    It emits only the first assistant phrase early. After that first flush it delegates
    back to Pipecat's normal simple aggregator in sentence or token mode.
    """

    def __init__(
        self,
        *,
        recorder: CallRecorder,
        timeout_ms: int,
        min_words: int,
        max_words: int,
        after_first_mode: str = "sentence",
    ) -> None:
        from pipecat.utils.text.base_text_aggregator import Aggregation, AggregationType
        from pipecat.utils.text.simple_text_aggregator import SimpleTextAggregator

        self._aggregation_cls = Aggregation
        self._recorder = recorder
        self._timeout_ms = max(0, timeout_ms)
        self._min_words = max(1, min_words)
        self._max_words = max(self._min_words, max_words)
        self._first_started_at: float | None = None
        self._first_flushed = False
        self._buffer = ""
        aggregation_type = (
            AggregationType.TOKEN if after_first_mode.lower() == "token" else AggregationType.SENTENCE
        )
        self._after_first = SimpleTextAggregator(aggregation_type=aggregation_type)

    @property
    def aggregation_type(self):
        return self._after_first.aggregation_type

    @property
    def text(self):
        if not self._first_flushed:
            return self._aggregation_cls(text=self._buffer.strip(" "), type="first_phrase")
        return self._after_first.text

    async def aggregate(self, text: str) -> AsyncIterator:
        if not text:
            return

        if self._first_flushed:
            async for aggregation in self._after_first.aggregate(text):
                yield aggregation
            return

        if self._first_started_at is None and text.strip():
            self._first_started_at = time.monotonic()

        self._buffer += text
        candidate = self._first_phrase_candidate()
        if not candidate and self._has_min_words():
            await self._wait_for_first_flush_timeout()
            candidate = self._first_phrase_candidate(force_timeout=True)

        if not candidate:
            return

        phrase, rest, reason = candidate
        self._first_flushed = True
        self._buffer = ""
        phrase = phrase.strip(" ")
        self._recorder.handle_first_speakable_phrase_sent(phrase, reason=reason)
        if phrase:
            yield self._aggregation_cls(text=phrase, type="first_phrase")

        if rest:
            async for aggregation in self._after_first.aggregate(rest):
                yield aggregation

    async def flush(self):
        if not self._first_flushed:
            text = self._buffer
            self._buffer = ""
            self._first_flushed = True
            if text.strip():
                self._recorder.handle_first_speakable_phrase_sent(text, reason="llm_end")
                return self._aggregation_cls(text=text.strip(" "), type="first_phrase")
            return None
        return await self._after_first.flush()

    async def handle_interruption(self):
        await self.reset()

    async def reset(self):
        self._first_started_at = None
        self._first_flushed = False
        self._buffer = ""
        await self._after_first.reset()

    async def _wait_for_first_flush_timeout(self) -> None:
        if self._timeout_ms <= 0 or self._first_started_at is None:
            return
        elapsed_ms = (time.monotonic() - self._first_started_at) * 1000
        remaining_ms = self._timeout_ms - elapsed_ms
        if remaining_ms > 0:
            await asyncio.sleep(remaining_ms / 1000)

    def _first_phrase_candidate(self, *, force_timeout: bool = False) -> tuple[str, str, str] | None:
        punctuation = PUNCTUATION_RE.search(self._buffer)
        if punctuation:
            end = punctuation.end()
            return self._buffer[:end], self._buffer[end:], "punctuation"

        if not force_timeout:
            return None

        words = self._complete_words()
        if len(words) < self._min_words:
            return None
        word_index = min(len(words), self._max_words) - 1
        end = words[word_index].end()
        return self._buffer[:end], self._buffer[end:], "timeout"

    def _has_min_words(self) -> bool:
        return len(self._complete_words()) >= self._min_words

    def _complete_words(self) -> list[re.Match[str]]:
        words = list(WORD_RE.finditer(self._buffer))
        if not words:
            return []
        last = words[-1]
        if last.end() == len(self._buffer) and not self._buffer.endswith(
            (" ", "\t", "\n", "\r", ".", "!", "?", ",", ";", ":")
        ):
            return words[:-1]
        return words
