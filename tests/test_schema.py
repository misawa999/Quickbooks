import pytest
from pydantic import ValidationError

from schema import Batch


def make_batch(**overrides):
    base = {
        "batch_id": "b1",
        "transactions": [
            {
                "line_id": "l1",
                "date": "2026-07-01",
                "lines": [
                    {"account": "Bank", "credit": 100},
                    {"account": "Expenses", "debit": 100},
                ],
            }
        ],
    }
    base.update(overrides)
    return base


def test_valid_home_currency_entry():
    batch = Batch.model_validate(make_batch())
    assert batch.transactions[0].currency is None


def test_valid_multicurrency_entry():
    data = make_batch(
        transactions=[
            {
                "line_id": "l1",
                "date": "2026-07-01",
                "currency": "CHF",
                "exchange_rate": 1.0962,
                "lines": [
                    {"account": "OCBC Bank (CHF)", "credit": 1250.00},
                    {"account": "Uncategorized Expenses", "debit": 1250.00},
                ],
            }
        ]
    )
    batch = Batch.model_validate(data)
    entry = batch.transactions[0]
    assert entry.currency == "CHF"
    assert float(entry.exchange_rate) == 1.0962


def test_unbalanced_entry_rejected():
    data = make_batch(
        transactions=[
            {
                "line_id": "l1",
                "date": "2026-07-01",
                "lines": [
                    {"account": "Bank", "credit": 100},
                    {"account": "Expenses", "debit": 99},
                ],
            }
        ]
    )
    with pytest.raises(ValidationError):
        Batch.model_validate(data)


def test_currency_without_rate_rejected():
    data = make_batch(
        transactions=[
            {
                "line_id": "l1",
                "date": "2026-07-01",
                "currency": "CHF",
                "lines": [
                    {"account": "Bank", "credit": 100},
                    {"account": "Expenses", "debit": 100},
                ],
            }
        ]
    )
    with pytest.raises(ValidationError):
        Batch.model_validate(data)


def test_negative_exchange_rate_rejected():
    data = make_batch(
        transactions=[
            {
                "line_id": "l1",
                "date": "2026-07-01",
                "currency": "CHF",
                "exchange_rate": -1.1,
                "lines": [
                    {"account": "Bank", "credit": 100},
                    {"account": "Expenses", "debit": 100},
                ],
            }
        ]
    )
    with pytest.raises(ValidationError):
        Batch.model_validate(data)


def test_line_with_both_debit_and_credit_rejected():
    data = make_batch(
        transactions=[
            {
                "line_id": "l1",
                "date": "2026-07-01",
                "lines": [
                    {"account": "Bank", "credit": 100, "debit": 100},
                    {"account": "Expenses", "debit": 100},
                ],
            }
        ]
    )
    with pytest.raises(ValidationError):
        Batch.model_validate(data)


def test_single_line_entry_rejected():
    data = make_batch(
        transactions=[
            {
                "line_id": "l1",
                "date": "2026-07-01",
                "lines": [{"account": "Bank", "credit": 100}],
            }
        ]
    )
    with pytest.raises(ValidationError):
        Batch.model_validate(data)


def test_duplicate_line_id_in_batch_rejected():
    data = make_batch(
        transactions=[
            {
                "line_id": "l1",
                "date": "2026-07-01",
                "lines": [
                    {"account": "Bank", "credit": 100},
                    {"account": "Expenses", "debit": 100},
                ],
            },
            {
                "line_id": "l1",
                "date": "2026-07-02",
                "lines": [
                    {"account": "Bank", "credit": 50},
                    {"account": "Expenses", "debit": 50},
                ],
            },
        ]
    )
    with pytest.raises(ValidationError):
        Batch.model_validate(data)


def test_empty_batch_rejected():
    with pytest.raises(ValidationError):
        Batch.model_validate(make_batch(transactions=[]))
