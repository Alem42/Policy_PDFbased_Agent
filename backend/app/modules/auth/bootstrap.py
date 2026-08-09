"""Create the one-time invitation used to register the first administrator."""

from app.modules.auth.invites import create_bootstrap_invite


def main() -> None:
    try:
        invite = create_bootstrap_invite()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("Initial administrator invitation (shown once):")
    print(invite["invite_code"])
    print(f"Expires at: {invite['expires_at'].isoformat()}")


if __name__ == "__main__":
    main()
