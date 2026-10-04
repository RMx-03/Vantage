"""Reissuing an email link must leave exactly one live link.

Cancelling the outstanding links and issuing the new one ran as two separate
transactions, so two simultaneous requests could both cancel and then both
issue, leaving two valid reset links in the mailbox.

To make the race deterministic, both requests are held at the moment they mint
their token. With separate transactions both have already cancelled by then,
so both new tokens survive. With one transaction that locks the user, the
second request cannot even start cancelling until the first commits, so the
hold times out and the second request cancels the first one's token.
"""

import threading
from uuid import uuid4

import pytest
from sqlalchemy import func, select

import app.repositories.email_tokens as email_tokens_module
from app.db.auth_models import EmailTokenRow
from app.db.session import SessionFactory
from app.repositories.users import UserRepository
from app.services.account import AccountService

pytestmark = pytest.mark.integration


class _NullSender:
    def send(self, message: object) -> None:
        pass


def _live(user_id: int, purpose: str) -> int:
    with SessionFactory() as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(EmailTokenRow)
                .where(
                    EmailTokenRow.user_id == user_id,
                    EmailTokenRow.purpose == purpose,
                    EmailTokenRow.consumed_at.is_(None),
                )
            ).scalar_one()
        )


@pytest.mark.parametrize(
    ("purpose", "trigger"),
    [
        (
            "password_reset",
            lambda accounts, user: accounts.request_password_reset(user.email),
        ),
        (
            "email_verification",
            lambda accounts, user: accounts.send_verification(user.id, user.email),
        ),
    ],
)
def test_concurrent_reissues_leave_one_live_link(
    purpose: str, trigger, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = UserRepository().create(
        email=f"race-{uuid4().hex}@example.com",
        password_hash="h",
        password_algo="argon2id",
    )
    hold = threading.Barrier(2)
    real_mint = email_tokens_module.mint_opaque_token

    def held_mint():
        try:
            hold.wait(timeout=1.5)
        except threading.BrokenBarrierError:
            pass
        return real_mint()

    monkeypatch.setattr(email_tokens_module, "mint_opaque_token", held_mint)
    accounts = AccountService(email_sender=_NullSender())

    workers = [
        threading.Thread(target=trigger, args=(accounts, user)) for _ in range(2)
    ]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=15)

    assert _live(user.id, purpose) == 1
