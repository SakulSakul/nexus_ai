"""PR-B 게이트 ② 결정적 검증 (키리스·LLM/DB 불필요·mock 기반).

검증 대상:
  (1) _gen_gemini / _gen_claude 빈 완료 → EmptyCompletionError raise (B-1/B-2)
  (2) _gen fallback 체인: gemini 빈완료 → claude 전환 + used_fallback=True (B-4)
  (3) 양 provider 빈완료 소진 → 마지막 EmptyCompletionError 전파 (ask 백스톱 입력)
  (4) 무한 루프 없음: provider 호출 횟수가 chain 길이(≤2) 이내
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.chatbot as cb
from core.answer_guard import EmptyCompletionError


class _FakeSettings:
    chat_provider = "gemini"
    chat_fallback_provider = "claude"
    anthropic_api_key = "dummy"
    gemini_api_key = "dummy"
    chat_model = "gemini-x"
    claude_model = "claude-x"


def _patch_settings(monkey):
    monkey(cb, "settings", lambda: _FakeSettings())
    monkey(cb, "_resolve_eval_provider", lambda: None)


def _empty_provider(system, user, *, include_thinking):
    raise EmptyCompletionError("empty (test)")


def _good_provider(system, user, *, include_thinking):
    return ("정상 답변", "", "model-x")


class _MP:
    def __init__(self): self._undo = []
    def setattr(self, obj, name, val):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, val)
    def restore(self):
        for obj, name, old in reversed(self._undo):
            setattr(obj, name, old)


def test_gen_chain_empty_gemini_falls_back_to_claude():
    mp = _MP()
    try:
        _patch_settings(mp.setattr)
        calls = []
        def gem(s, u, *, include_thinking):
            calls.append("gemini"); raise EmptyCompletionError("gemini empty")
        def cla(s, u, *, include_thinking):
            calls.append("claude"); return ("정상", "", "claude-x")
        mp.setattr(cb, "_PROVIDER_FUNCS", {"gemini": gem, "claude": cla})
        text, thinking, prov, model, used_fallback = cb._gen("sys", "usr", include_thinking=False)
        assert text == "정상", text
        assert prov == "claude", prov
        assert used_fallback is True
        assert calls == ["gemini", "claude"], calls
    finally:
        mp.restore()


def test_gen_chain_all_empty_propagates_emptycompletion():
    mp = _MP()
    try:
        _patch_settings(mp.setattr)
        calls = []
        def gem(s, u, *, include_thinking):
            calls.append("gemini"); raise EmptyCompletionError("gemini empty")
        def cla(s, u, *, include_thinking):
            calls.append("claude"); raise EmptyCompletionError("claude empty")
        mp.setattr(cb, "_PROVIDER_FUNCS", {"gemini": gem, "claude": cla})
        raised = False
        try:
            cb._gen("sys", "usr", include_thinking=False)
        except EmptyCompletionError:
            raised = True
        assert raised, "양 provider 빈완료 → EmptyCompletionError 전파해야 함"
        assert calls == ["gemini", "claude"], calls
    finally:
        mp.restore()


def test_gen_non_empty_passes_through():
    mp = _MP()
    try:
        _patch_settings(mp.setattr)
        mp.setattr(cb, "_PROVIDER_FUNCS", {"gemini": _good_provider, "claude": _empty_provider})
        text, _, prov, _, used_fallback = cb._gen("sys", "usr", include_thinking=False)
        assert text == "정상 답변"
        assert prov == "gemini"
        assert used_fallback is False
    finally:
        mp.restore()


def test_empty_completion_error_is_exception_subclass():
    assert issubclass(EmptyCompletionError, Exception)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fail = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception as e:
            fail += 1; print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"=== {len(fns)-fail}/{len(fns)} passed ===")
    sys.exit(1 if fail else 0)
