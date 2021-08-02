# from ..backends.base import AsyncNetworkBackend
# from ..urls import Origin
# from.connection_pool import AsyncConnectionPool
# from .interfaces import AsyncConnectionInterface
# from .models import AsyncRawRequest, AsyncRawResponse
# import ssl
#
#
# class AsyncHTTPProxy(AsyncConnectionPool):
#     def __init__(
#         self,
#         proxy_origin: Origin,
#         ssl_context: ssl.SSLContext = None,
#         max_connections: int = 10,
#         max_keepalive_connections: int = None,
#         keepalive_expiry: float = None,
#         network_backend: AsyncNetworkBackend = None,
#     ) -> None:
#         super().__init__(
#             ssl_context=ssl_context,
#             max_connections=max_connections,
#             max_keepalive_connections=max_keepalive_connections,
#             keepalive_expiry=keepalive_expiry,
#             network_backend=network_backend
#         )
#         self._proxy_origin = proxy_origin
#
#     def get_origin(self) -> Origin:
#         return self._proxy_origin
#
#     def create_connection(self, origin: Origin) -> AsyncConnectionInterface:
#         return AsyncForwardHTTPConnection(
#             proxy_origin=self._proxy_origin,
#             keepalive_expiry=self._keepalive_expiry,
#             network_backend=self._network_backend,
#         )
#
#
# class AsyncForwardHTTPConnection(AsyncConnectionInterface):
#     def __init__(
#         self,
#         proxy_origin: Origin,
#         keepalive_expiry: float = None,
#         network_backend: AsyncNetworkBackend = None,
#     ) -> None:
#         self.proxy_origin = proxy_origin
#         self._connection = AsyncHTTPConnection(
#             origin=proxy_origin,
#             keepalive_expiry=keepalive_expiry,
#             network_backend=network_backend
#         )
#
#     async def handle_async_request(self, request: AsyncRawRequest) -> AsyncRawResponse:
#         proxy_url = RawURL(
#             scheme=self.proxy_origin.scheme,
#             host=self.proxy_origin.host,
#             port=self.proxy_origin.port,
#             target=bytes(request.url)
#         )
#         proxy_request = RawRequest(
#             method=request.method,
#             url=proxy_url,
#             headers=self.proxy_headers + request.headers,
#             stream=request.stream,
#             extensions=request.extensions
#         )
#         return await self._connection.handle_async_request(proxy_request)
#
#     async def aclose(self):
#         await self._connection.aclose()
#
#     async def attempt_aclose(self) -> bool:
#         await self._connection.attempt_aclose()
#
#     def info(self) -> str:
#         return self._connection.info()
#
#     def get_origin(self) -> Origin:
#         return self.proxy_origin
#
#     def is_available(self) -> bool:
#         return self._connection.is_available()
#
#     def has_expired(self) -> bool:
#         return self._connection.has_expired()
#
#     def is_idle(self) -> bool:
#         return self._connection.is_idle()
#
#     def is_closed(self) -> bool:
#         return self._connection.is_closed()
