"""
Generate a self-signed TLS certificate for HTTPS.

Creates certs/server.key and certs/server.crt valid for localhost, 127.0.0.1,
your LAN IP and this machine's hostname.

Usage:
    python make_cert.py
    python make_cert.py --days 825 --host 192.168.1.230 --host mypc

The certificate is self-signed, so clients will warn unless the CA is trusted.
On Windows you can trust it for PowerShell/curl with:
    Import-Certificate -FilePath certs\\server.crt -CertStoreLocation Cert:\\CurrentUser\\Root
(requires admin for LocalMachine)
"""

import argparse
import datetime
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from config import BASE_DIR

CERT_DIR = BASE_DIR / "certs"


def main(args):
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    key_path = CERT_DIR / "server.key"
    cert_path = CERT_DIR / "server.crt"

    hostname = socket.gethostname()
    hosts = {"localhost", "127.0.0.1", hostname}
    for extra in args.host:
        hosts.add(extra)
    try:
        for info in socket.getaddrinfo(hostname, None):
            hosts.add(info[4][0])
    except Exception:
        pass

    # Classify each host so IP addresses get an IP SAN and names get a DNS SAN.
    dns_names, ip_names = set(), set()
    for host in hosts:
        try:
            ip_names.add(ipaddress.ip_address(host))
        except ValueError:
            dns_names.add(host)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Yeeps Private Server"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=args.days))
        .add_extension(
            x509.SubjectAlternativeName([
                *[x509.DNSName(n) for n in sorted(dns_names)],
                *[x509.IPAddress(i) for i in sorted(ip_names, key=str)],
            ]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Certificate written for: {', '.join(sorted(dns_names))}")
    print(f"                       + {', '.join(str(i) for i in sorted(ip_names, key=str))}")
    print(f"\n  {cert_path}")
    print(f"  {key_path}")
    print(f"\nValid for {args.days} days.")
    print("\nTo trust it on this machine (PowerShell, admin needed for LocalMachine):")
    print(f'  Import-Certificate -FilePath "{cert_path}" -CertStoreLocation Cert:\\CurrentUser\\Root')
    print("\nThen start the server with HTTPS:")
    print("  set USE_SSL=1 && python main.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a self-signed TLS certificate.")
    parser.add_argument("--days", type=int, default=825, help="validity in days")
    parser.add_argument("--host", action="append", default=[],
                        help="extra hostname or IP to include (repeatable)")
    main(parser.parse_args())