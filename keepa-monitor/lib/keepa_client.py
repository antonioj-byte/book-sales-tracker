from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import keepa

logger = logging.getLogger(__name__)

# Costes oficiales Keepa (aprox.) usados para presupuesto previo a cada llamada
TOKEN_COST_PRODUCT = 1
TOKEN_COST_BEST_SELLERS = 50
TOKEN_COST_CATEGORY_LOOKUP = 2


@dataclass
class TokenBudget:
    max_tokens_per_run: int
    tokens_before: int
    tokens_spent: int = 0
    _last_tokens_left: int = field(repr=False, default=0)
    calls: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_api(cls, api: keepa.Keepa, max_tokens_per_run: int) -> TokenBudget:
        tokens_left = int(api.tokens_left)
        return cls(
            max_tokens_per_run=max_tokens_per_run,
            tokens_before=tokens_left,
            _last_tokens_left=tokens_left,
        )

    def check_budget(self, estimated_cost: int, label: str) -> None:
        if self.tokens_spent + estimated_cost > self.max_tokens_per_run:
            raise TokenBudgetExceeded(
                f"Presupuesto de tokens superado antes de {label}: "
                f"gastados={self.tokens_spent}, estimado={estimated_cost}, "
                f"max={self.max_tokens_per_run}"
            )

    def after_call(self, api: keepa.Keepa, label: str, estimated: int) -> None:
        current = int(api.tokens_left)
        actual = self._last_tokens_left - current
        if actual < 0:
            actual = estimated
        self.tokens_spent += actual
        self._last_tokens_left = current
        entry = {
            "label": label,
            "estimated_tokens": estimated,
            "actual_tokens": actual,
            "tokens_left": current,
        }
        self.calls.append(entry)
        logger.info(
            "%s | estimado=%s real=%s restantes=%s",
            label,
            estimated,
            actual,
            current,
        )

    @property
    def tokens_after(self) -> int | None:
        return self._last_tokens_left if self.calls else None


class TokenBudgetExceeded(Exception):
    pass


def create_keepa_client(api_key: str) -> keepa.Keepa:
    return keepa.Keepa(api_key)


def domain_to_keepa(domain_id: int) -> str:
    mapping = {
        1: "US",
        2: "GB",
        3: "DE",
        4: "FR",
        5: "JP",
        6: "CA",
        8: "IT",
        9: "ES",
        10: "IN",
        11: "MX",
    }
    if domain_id not in mapping:
        raise ValueError(f"domain_id Keepa no soportado: {domain_id}")
    return mapping[domain_id]
