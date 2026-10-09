"""Error types. One failing provider must never kill a run."""


class PriceHunterError(Exception):
    pass


class ProviderError(PriceHunterError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider


class ProviderNotConfigured(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    pass


class ResolverError(PriceHunterError):
    pass
