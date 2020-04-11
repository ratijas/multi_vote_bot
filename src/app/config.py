import os
import sys
from dataclasses import asdict, dataclass, replace
from typing import Optional
from abc import ABCMeta, abstractmethod


class ConfigurationError(RuntimeError):
    pass


class ConfigurationSource(metaclass=ABCMeta):

    @abstractmethod
    def token(self) -> Optional[str]:
        pass

    @abstractmethod
    def webhook_url(self) -> Optional[str]:
        pass

    @abstractmethod
    def port(self) -> Optional[int]:
        pass

    @abstractmethod
    def listen(self) -> Optional[str]:
        pass

    def partial(self) -> 'PartialConfiguration':
        return PartialConfiguration(
            token=self.token(),
            webhook_url=self.webhook_url(),
            port=self.port(),
            listen=self.listen(),
        )


class EnvConfigurationSource(ConfigurationSource):

    def get_raw(self, key: str) -> Optional[str]:
        return os.getenv(key)

    def get_int(self, key: str) -> Optional[int]:
        raw = self.get_raw(key)
        if raw is not None:
            return int(raw)

    def token(self) -> Optional[str]:
        return self.get_raw('TOKEN')

    def webhook_url(self) -> Optional[str]:
        return self.get_raw('WEBHOOK_URL')

    def port(self) -> Optional[int]:
        return self.get_int('PORT')

    def listen(self) -> Optional[str]:
        return self.get_raw('LISTEN')


@dataclass
class PartialConfiguration:
    """Everything is Optional."""
    token: Optional[str]
    webhook_url: Optional[str]
    port: Optional[int]
    listen: Optional[str]

    def merge_from(self, other: 'PartialConfiguration') -> 'PartialConfiguration':
        d = {
            key: value
            for key, value in asdict(other).items()
            if value is not None
        }
        return replace(self, **d)

    def build(self) -> 'Configuration':
        if self.token is None:
            raise ConfigurationError("Required configuration not found: TOKEN")
        return Configuration(
            token=self.token,
            webhook_url=self.webhook_url,
            port=self.port,
            listen=self.listen,
        )


@dataclass
class Configuration:
    token: str
    webhook_url: Optional[str]
    port: Optional[int]
    listen: Optional[str]

    @classmethod
    def get_from_env(cls) -> 'PartialConfiguration':
        source = EnvConfigurationSource()
        return source.partial()

    @classmethod
    def get(cls) -> 'Configuration':
        """
        Merge and get combined configuration from environment and command line options.

        NOTE: currently supports only environment variables.
        """
        builder = PartialConfiguration(None, None, None, None)

        partial = cls.get_from_env()
        builder = builder.merge_from(partial)

        return builder.build()
