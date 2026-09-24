"""
STORY FORGE — Safe URL Validator (SSRF Protection)
==================================================
Strict URL sanitization and SSRF (Server-Side Request Forgery) guard.
Blocks private subnets, loopback addresses, cloud metadata services,
and forbidden protocol schemas before initiating HTTP/HTTPS fetches.
"""

import ipaddress
import socket
import urllib.parse
from typing import Tuple, Set, List


class SafeURLValidator:
    """
    Validates URLs to defend against SSRF and illegal resource access.
    """

    ALLOWED_SCHEMES: Set[str] = {"http", "https"}

    BLOCKED_HOSTNAMES: Set[str] = {
        "localhost",
        "127.0.0.1",
        "::1",
        "metadata.google.internal",
        "169.254.169.254",
        "instance-data",
    }

    # STORY FORGE Policy: Never acquire from generic or commercial stock providers
    DISALLOWED_STOCK_DOMAINS: Set[str] = {
        "pexels.com",
        "unsplash.com",
        "pixabay.com",
        "shutterstock.com",
        "gettyimages.com",
        "istockphoto.com",
        "stock.adobe.com",
        "storyblocks.com",
        "videvo.net",
        "freepik.com",
    }

    PRIVATE_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    @classmethod
    def is_safe_url(cls, url: str, resolve_dns: bool = False) -> Tuple[bool, str]:
        """
        Validates URL safety against SSRF attacks.

        Args:
            url: The candidate URL string.
            resolve_dns: If True, performs DNS lookup to ensure resolved IP is not private.

        Returns:
            Tuple of (is_safe: bool, reason: str)
        """
        if not url or not isinstance(url, str):
            return False, "Empty or non-string URL"

        url_str = url.strip()
        try:
            parsed = urllib.parse.urlparse(url_str)
        except Exception as exc:
            return False, f"Malformed URL syntax: {exc}"

        scheme = (parsed.scheme or "").lower()
        if scheme not in cls.ALLOWED_SCHEMES:
            return False, f"Prohibited scheme '{scheme}'. Only HTTP and HTTPS allowed."

        hostname = (parsed.hostname or "").lower().strip()
        if not hostname:
            return False, "URL contains no valid hostname"

        if hostname in cls.BLOCKED_HOSTNAMES:
            return False, f"Prohibited hostname '{hostname}'"

        for stock_domain in cls.DISALLOWED_STOCK_DOMAINS:
            if hostname == stock_domain or hostname.endswith("." + stock_domain):
                return False, f"STORY FORGE Policy: Stock media provider '{stock_domain}' is strictly prohibited."

        # Check direct IP literals in hostname
        try:
            ip_obj = ipaddress.ip_address(hostname)
            for net in cls.PRIVATE_NETWORKS:
                if ip_obj in net:
                    return False, f"IP literal '{ip_obj}' falls within restricted private network {net}"
        except ValueError:
            # Not an IP literal, it is a standard domain name
            pass

        # Optional DNS resolution to protect against DNS rebinding
        if resolve_dns:
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for item in addr_info:
                    resolved_ip_str = item[4][0]
                    resolved_ip = ipaddress.ip_address(resolved_ip_str)
                    for net in cls.PRIVATE_NETWORKS:
                        if resolved_ip in net:
                            return False, f"Hostname '{hostname}' resolved to restricted IP {resolved_ip}"
            except Exception as dns_err:
                return False, f"DNS resolution failed for '{hostname}': {dns_err}"

        return True, "URL is safe"
