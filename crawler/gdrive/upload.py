#!/usr/bin/env python3
"""
gdrive/upload.py — Google Drive 업로드 스크립트

data/ 폴더의 JSON 메타데이터와 이미지를 Google Drive에 업로드합니다.

구조:
  Drive: seoulfit-data/
    ├── metadata/
    │   ├── products_enriched.json   ← 서버가 시작 시 로드
    │   └── gallery-index.json       ← 이미지 파일ID 매핑
    └── images/
        ├── wconcept/
        └── 29cm/

사전 준비:
  1. Google Cloud Console → APIs → Drive API 활성화
  2. 서비스 계정 생성 → JSON 키 다운로드 → gdrive/service_account.json 으로 저장
  3. Drive 폴더 생성 → 서비스 계정 이메일에 편집자 권한 부여
  4. .env 에 GDRIVE_FOLDER_ID=폴더ID 설정

사용법:
  python gdrive/upload.py                     # metadata + 이미지 전체 업로드
  python gdrive/upload.py --metadata-only     # JSON 메타데이터만 업로드
  python gdrive/upload.py --images-only       # 이미지만 업로드
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

SERVICE_ACCOUNT_PATH = os.getenv(
    "GDRIVE_SERVICE_ACCOUNT_PATH",
    str(Path(__file__).resolve().parent / "service_account.json"),
)
ROOT_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")


def _get_drive_service():
    """Google Drive API 서비스 객체 반환."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "google-api-python-client, google-auth 패키지가 필요합니다.\n"
            "  pip install google-api-python-client google-auth google-auth-httplib2"
        )

    if not Path(SERVICE_ACCOUNT_PATH).exists():
        raise FileNotFoundError(
            f"서비스 계정 파일을 찾을 수 없습니다: {SERVICE_ACCOUNT_PATH}\n"
            "gdrive/service_account.json 을 확인하세요."
        )

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_PATH,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=creds)


def _get_or_create_folder(service, name: str, parent_id: str) -> str:
    """폴더가 있으면 ID 반환, 없으면 생성 후 반환."""
    query = (
        f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
        f" and '{parent_id}' in parents and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    print(f"  [Drive] 폴더 생성: {name}")
    return folder["id"]


def _upload_file(service, local_path: Path, folder_id: str, overwrite: bool = True) -> str:
    """파일 업로드. overwrite=True이면 기존 파일 덮어쓰기. 파일 ID 반환."""
    from googleapiclient.http import MediaFileUpload

    mime = "application/json" if local_path.suffix == ".json" else "image/jpeg"
    media = MediaFileUpload(str(local_path), mimetype=mime)

    # 기존 파일 확인
    if overwrite:
        query = f"name='{local_path.name}' and '{folder_id}' in parents and trashed=false"
        existing = service.files().list(q=query, fields="files(id)").execute().get("files", [])
        if existing:
            file_id = existing[0]["id"]
            service.files().update(fileId=file_id, media_body=media).execute()
            return file_id

    file_meta = {"name": local_path.name, "parents": [folder_id]}
    file = service.files().create(body=file_meta, media_body=media, fields="id").execute()
    return file["id"]


def upload_metadata(service, root_folder_id: str) -> dict[str, str]:
    """metadata/ 폴더에 JSON 파일 업로드. {파일명: fileId} 반환."""
    meta_folder_id = _get_or_create_folder(service, "metadata", root_folder_id)
    file_id_map: dict[str, str] = {}

    for json_file in ["products_enriched.json", "products_raw.json"]:
        local = DATA_DIR / json_file
        if not local.exists():
            print(f"  [건너뜀] {json_file} 파일 없음")
            continue
        print(f"  [업로드] {json_file} ({local.stat().st_size / 1024:.1f} KB)...")
        file_id = _upload_file(service, local, meta_folder_id)
        file_id_map[json_file] = file_id
        print(f"    → Drive ID: {file_id}")

    return file_id_map


def upload_images(service, root_folder_id: str) -> dict[str, str]:
    """images/ 폴더에 이미지 업로드. {파일명: fileId} 반환."""
    images_folder_id = _get_or_create_folder(service, "images", root_folder_id)
    file_id_map: dict[str, str] = {}
    image_dir = ROOT.parent / "images"  # 프로젝트 루트 images/ 폴더

    if not image_dir.exists():
        print(f"  [건너뜀] images/ 폴더 없음: {image_dir}")
        return {}

    for mall_dir in sorted(image_dir.iterdir()):
        if not mall_dir.is_dir():
            continue
        mall_folder_id = _get_or_create_folder(service, mall_dir.name, images_folder_id)
        images = list(mall_dir.glob("*.jpg")) + list(mall_dir.glob("*.png")) + list(mall_dir.glob("*.webp"))
        print(f"  [{mall_dir.name}] {len(images)}개 이미지 업로드...")
        for img in images:
            file_id = _upload_file(service, img, mall_folder_id)
            file_id_map[f"{mall_dir.name}/{img.name}"] = file_id

    return file_id_map


def save_gallery_index(service, root_folder_id: str, image_id_map: dict[str, str]) -> None:
    """gallery-index.json 생성 후 Drive 업로드."""
    meta_folder_id = _get_or_create_folder(service, "metadata", root_folder_id)
    index_path = DATA_DIR / "gallery-index.json"
    index_path.write_text(
        json.dumps(image_id_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _upload_file(service, index_path, meta_folder_id)
    print(f"  [gallery-index.json] {len(image_id_map)}개 이미지 ID 저장 완료")


def main() -> None:
    parser = argparse.ArgumentParser(description="SEOULFIT → Google Drive 업로드")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--images-only", action="store_true")
    args = parser.parse_args()

    if not ROOT_FOLDER_ID:
        print("[오류] .env 에 GDRIVE_FOLDER_ID 를 설정해주세요.")
        return

    print("[Google Drive] 연결 중...")
    service = _get_drive_service()
    print("  연결 성공.")

    if not args.images_only:
        print("\n[메타데이터 업로드]")
        upload_metadata(service, ROOT_FOLDER_ID)

    if not args.metadata_only:
        print("\n[이미지 업로드]")
        image_id_map = upload_images(service, ROOT_FOLDER_ID)
        if image_id_map:
            save_gallery_index(service, ROOT_FOLDER_ID, image_id_map)

    print("\n[완료] Google Drive 업로드 완료.")
    print(f"  Drive 폴더: https://drive.google.com/drive/folders/{ROOT_FOLDER_ID}")


if __name__ == "__main__":
    main()
