from app.config import settings


if __name__ == "__main__":
    path = settings.get_document_with_path("helo")
    print(path)
    print(type(path))