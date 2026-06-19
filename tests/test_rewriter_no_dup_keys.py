"""F601 회귀 가드 + merge 보존 가드 (keyless, AST 기반 — 패키지 import 없음)."""
import ast
import os

_SRC = os.path.join(os.path.dirname(__file__), "..", "core", "nexus_query_rewriter.py")


def _tree():
    with open(_SRC, encoding="utf-8") as f:
        return ast.parse(f.read())


def _duplicate_literal_keys():
    dups = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Dict):
            seen = set()
            for k in node.keys:
                if isinstance(k, ast.Constant):
                    if k.value in seen:
                        dups.append((k.value, k.lineno))
                    seen.add(k.value)
    return dups


def _incident_nodes_map():
    out = {}
    for node in ast.walk(_tree()):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
                and node.targets and getattr(node.targets[0], "id", None) == "_NEXUS_NL_TO_INCIDENT_NODES"):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant):
                    out[k.value] = ast.literal_eval(v)
    return out


def test_no_duplicate_literal_keys():
    assert _duplicate_literal_keys() == [], f"중복 리터럴 키: {_duplicate_literal_keys()}"


def test_merge_preserves_both_mappings():
    m = _incident_nodes_map()
    assert ("근무기강", "성희롱") in m["성희롱"] and ("성희롱", "윤리보고") in m["성희롱"], m["성희롱"]
    assert ("근무기강", "괴롭힘") in m["갑질"] and ("괴롭힘", "윤리보고") in m["갑질"], m["갑질"]
    assert ("조직관리", "횡령수수") in m["횡령"] and ("윤리보고", None) in m["횡령"], m["횡령"]
