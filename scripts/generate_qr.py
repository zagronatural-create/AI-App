#!/usr/bin/env python3
import argparse
import json

import qrcode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-code", required=True)
    parser.add_argument("--product-sku", default="TRAD-NUTRI-500G")
    parser.add_argument("--mfg-date", default="2026-02-20")
    parser.add_argument("--trace-url", default=None)
    parser.add_argument("--out", default="batch-qr.png")
    args = parser.parse_args()

    payload = {
        "batchCode": args.batch_code,
        "productSku": args.product_sku,
        "mfgDate": args.mfg_date,
        "traceUrl": args.trace_url or f"https://ops.example.com/trace/{args.batch_code}",
    }
    img = qrcode.make(json.dumps(payload))
    img.save(args.out)
    print(f"Wrote QR image to {args.out}")


if __name__ == "__main__":
    main()
