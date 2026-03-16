# pip3 install tokenizers
# python3 deepseek_tokenizer.py
from pathlib import Path

from tokenizers import Tokenizer

chat_tokenizer_dir = Path(__file__).resolve().parent
tokenizer = Tokenizer.from_file(str(chat_tokenizer_dir / "tokenizer.json"))

result = tokenizer.encode("Hello!")
print(result.ids)
