from mainapp.models import Character, Worldbook, ChatSettings
import json


# def build_ai_request(user, character: Character, chat_settings: ChatSettings):
#     """
#     Формує JSON-запит для моделі ШІ (структурований і читабельний).
#     """
#
#     # 1. Завантажуємо ChatSettings JSON
#     settings_data = {}
#     if chat_settings and chat_settings.json_file and hasattr(chat_settings.json_file, "path"):
#         try:
#             with open(chat_settings.json_file.path, "r", encoding="utf-8") as f:
#                 settings_data = json.load(f)
#         except Exception:
#             settings_data = {}
#
#     # Витягуємо ядро (core) і системні промпти
#     core_keys = {"max_tokens", "seed", "sampling"}
#     core_data = {k: settings_data[k] for k in core_keys if k in settings_data}
#     system_prompts = {k: v for k, v in settings_data.items() if k not in core_keys}
#
#     # 2. Character description
#     character_data = {
#         "name": character.name,
#         "description": character.description,
#         "scenario": character.scenario,
#         "initial_message": character.initial_message,
#         "creator_notes": character.creator_notes,
#     }
#
#     # 3. Chat history та останнє повідомлення користувача
#     chat_history = []
#     last_user_message = None
#     if character.chat_log_file and hasattr(character.chat_log_file, "path"):
#         try:
#             with open(character.chat_log_file.path, "r", encoding="utf-8") as f:
#                 messages = json.load(f)
#
#             # Знайти всі повідомлення користувача
#             user_messages = [msg for msg in messages if msg[0] == "user"]
#
#             if user_messages:
#                 last_user_message = user_messages[-1]  # останнє
#
#                 # ChatHistory = останні 5 перед останнім user
#                 last_user_index = messages.index(last_user_message)
#                 chat_history = messages[max(0, last_user_index - 5):last_user_index]
#
#         except Exception:
#             chat_history = []
#             last_user_message = None
#
#     # 4. User persona
#     user_persona = {
#         "persona_name": getattr(user, "persona_name", None),
#         "persona_description": getattr(user, "persona_description", None),
#         "name": getattr(user, "name", user.username),
#         "date_birth": user.date_birth.isoformat() if getattr(user, "date_birth", None) else None,
#     }
#
#     # Формуємо фінальний JSON
#     ai_request = {
#         "Core": core_data,
#         "SystemPrompts": system_prompts,
#         "CharacterDescription": character_data,
#         "ChatHistory": chat_history,
#         "LastUserMessage": last_user_message,
#         "UserPersona": user_persona,
#     }
#
#     # 🔹 Вивід у консоль у красивому форматі
#     #print("\n=== AI REQUEST JSON ===")
#     #print(json.dumps(ai_request, indent=4, ensure_ascii=False))
#     #print("=======================\n")
#
#     return ai_request

#=======================================

# def build_ai_request(user, character: Character, chat_settings: ChatSettings, worldbook_slug=None):
#     """
#     Формує JSON-запит для моделі ШІ (структурований і читабельний).
#     """
#
#     # 1. Завантажуємо ChatSettings JSON
#     settings_data = {}
#     if chat_settings and chat_settings.json_file and hasattr(chat_settings.json_file, "path"):
#         try:
#             with open(chat_settings.json_file.path, "r", encoding="utf-8") as f:
#                 settings_data = json.load(f)
#         except Exception:
#             settings_data = {}
#
#     # Витягуємо ядро (core) і системні промпти
#     core_keys = {"max_tokens", "seed", "sampling"}
#     core_data = {k: settings_data[k] for k in core_keys if k in settings_data}
#     system_prompts = {k: v for k, v in settings_data.items() if k not in core_keys}
#
#     # 2. Character description
#     character_data = {
#         "name": character.name,
#         "description": character.description,
#         "scenario": character.scenario,
#         "initial_message": character.initial_message,
#         "creator_notes": character.creator_notes,
#     }
#
#     # 3. Chat history та останнє повідомлення користувача
#     chat_history = []
#     last_user_message = None
#     if character.chat_log_file and hasattr(character.chat_log_file, "path"):
#         try:
#             with open(character.chat_log_file.path, "r", encoding="utf-8") as f:
#                 messages = json.load(f)
#
#             user_messages = [msg for msg in messages if msg[0] == "user"]
#
#             if user_messages:
#                 last_user_message = user_messages[-1]
#
#                 last_user_index = messages.index(last_user_message)
#                 chat_history = messages[max(0, last_user_index - 5):last_user_index]
#
#         except Exception:
#             chat_history = []
#             last_user_message = None
#
#     # 4. User persona
#     user_persona = {
#         "persona_name": getattr(user, "persona_name", None),
#         "persona_description": getattr(user, "persona_description", None),
#         "name": getattr(user, "name", user.username),
#         "date_birth": user.date_birth.isoformat() if getattr(user, "date_birth", None) else None,
#     }
#
#     # 5. Worldbook matches
#     worldbook_matches = []
#     if last_user_message and worldbook_slug:
#         try:
#             worldbook_matches = get_worldbook_matches(last_user_message[2], worldbook_slug, top_k=5)
#         except Exception as e:
#             print(f"Worldbook match error: {e}")
#             worldbook_matches = []
#
#     # Формуємо фінальний JSON
#     ai_request = {
#         "Core": core_data,
#         "SystemPrompts": system_prompts,
#         "CharacterDescription": character_data,
#         "ChatHistory": chat_history,
#         "LastUserMessage": last_user_message,
#         "UserPersona": user_persona,
#         "WorldbookMatches": worldbook_matches,   # 🔹 новий блок
#     }
#     print("З ФУНКЦІЇ")
#     print(ai_request)
#
#
#     return ai_request


import io
import json
import numpy as np
from sentence_transformers import util

# def get_worldbook_matches(message, worldbook_slug, top_k=5):
#     print("INFO====================")
#     print(message, worldbook_slug)
#
#     try:
#         wb = Worldbook.objects.get(slug=worldbook_slug)
#     except Worldbook.DoesNotExist:
#         return []
#
#     if not wb.json_file:
#         return []
#
#     # Відкриваємо файл як текстовий
#     with wb.json_file.open('rb') as f:
#         text = io.TextIOWrapper(f, encoding='utf-8').read()
#         data = json.loads(text)
#
#     keys = list(data.keys())
#     values = list(data.values())
#
#     # Створюємо ембедінги для ключів
#     key_embeddings = model.encode(keys, convert_to_tensor=True)
#     message_embedding = model.encode(message, convert_to_tensor=True)
#
#     # Обчислюємо схожість косинусом
#     cos_scores = util.cos_sim(message_embedding, key_embeddings)[0]
#
#     # Вибираємо топ-k найбільш схожих
#     top_results = np.argpartition(-cos_scores, range(top_k))[:top_k]
#
#     results = []
#     for idx in top_results:
#         results.append({
#             "key": keys[idx],
#             "value": values[idx],
#             "similarity": float(cos_scores[idx])
#         })
#
#     # Сортуємо за схожістю
#     results = sorted(results, key=lambda x: x['similarity'], reverse=True)
#
#     return results
#

# def get_worldbook_matches(message, worldbook_slug, top_k=5, similarity_threshold=0.1):
#     print("INFO-----------",message, worldbook_slug)
#     try:
#         wb = Worldbook.objects.get(slug=worldbook_slug)
#     except Worldbook.DoesNotExist:
#         print("Worldbook.DoesNotExist")
#         return {"AdditionalContext": []}
#
#     if not wb.json_file:
#         print("not wb.json_file")
#         return {"AdditionalContext": []}
#
#     # Читаємо JSON файл
#     with wb.json_file.open('rb') as f:
#         text = io.TextIOWrapper(f, encoding='utf-8').read()
#         data = json.loads(text)
#
#     # Беремо лише пари ключ-значення, що є "текстовими"
#     key_value_pairs = {k: v for k, v in data.items() if isinstance(v, (str, int, float))}
#
#     if not key_value_pairs:
#         print("not key_value_pairs")
#         return {"AdditionalContext": []}
#
#     keys = list(key_value_pairs.keys())
#     values = list(key_value_pairs.values())
#
#     print("KeysVALUES", keys, values)
#
#     # Створюємо ембедінги
#     key_embeddings = model.encode(keys, convert_to_tensor=True)
#     message_embedding = model.encode(message, convert_to_tensor=True)
#
#     # Косинусна схожість
#     cos_scores = util.cos_sim(message_embedding, key_embeddings)[0]
#
#     results = []
#
#     # Створюємо список (index, score) для тих, що перевищують поріг 0.7
#     valid_scores = [(idx, float(score)) for idx, score in enumerate(cos_scores) if score > 0.7]
#
#     # Сортуємо за схожістю
#     valid_scores.sort(key=lambda x: x[1], reverse=True)
#
#     # Беремо лише топ-K
#     top_indices = [idx for idx, _ in valid_scores[:top_k]]
#
#     # Формуємо фінальний список ключ-значення
#     for idx in top_indices:
#         results.append({
#             "key": keys[idx],
#             "value": values[idx]
#         })
#
#     return results

#=======================================================

# from openai import OpenAI
# import numpy as np
#
# # Ініціалізація клієнта OpenAI
# client = OpenAI(api_key="YOUR_OPENAI_API_KEY")  # або через env OPENAI_API_KEY
#
# def get_similar_keys(text, keywords, similarity_threshold=0.7):
#     """
#     text: str, користувацький текст
#     keywords: list[str], список ключових слів
#     similarity_threshold: float, поріг схожості
#     """
#     # Отримуємо embedding для тексту
#     text_embedding = client.embeddings.create(
#         model="text-embedding-3-small",
#         input=text
#     )['data'][0]['embedding']
#
#     # Отримуємо embedding для кожного ключа
#     key_embeddings = client.embeddings.create(
#         model="text-embedding-3-small",
#         input=keywords
#     )['data']
#
#     # Косинусна схожість
#     def cosine_sim(a, b):
#         a = np.array(a)
#         b = np.array(b)
#         return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
#
#     similar_keys = []
#     for idx, k_emb in enumerate(key_embeddings):
#         sim = cosine_sim(text_embedding, k_emb['embedding'])
#         if sim >= similarity_threshold:
#             similar_keys.append(keywords[idx])
#
#     return similar_keys
#
# # --- Приклад використання ---
# text = "I love eating pasta and fresh bread with poppy seeds"
# keywords = ["булочка з маком", "pasta", "cheese", "milk", "bread"]
#
# matches = get_similar_keys(text, keywords, similarity_threshold=0.6)
# print(matches)

#=====================================================




def get_worldbook_matches(message, worldbook_slug, top_k=5, similarity_threshold=0.01):
    print("INFO-----------", message, worldbook_slug)

    try:
        wb = Worldbook.objects.get(slug=worldbook_slug)
    except Worldbook.DoesNotExist:
        print("Worldbook.DoesNotExist")
        return {"AdditionalContext": []}

    if not wb.json_file:
        print("not wb.json_file")
        return {"AdditionalContext": []}

    # Читаємо JSON файл
    with wb.json_file.open('rb') as f:
        text = io.TextIOWrapper(f, encoding='utf-8').read()
        data = json.loads(text)

    # Збираємо всі пари key/value з верхнього рівня та з entries
    keys = []
    values = []

    # Верхній рівень
    for k, v in data.items():
        if k == "entries":
            continue  # обробимо окремо
        keys.append(k)
        values.append(v)

    # Вкладений список entries
    for entry in data.get("entries", []):
        if "key" in entry and "value" in entry:
            keys.append(entry["key"])
            values.append(entry["value"])

    if not keys:
        return {"AdditionalContext": []}

    print("Keys:", keys)
    print("Values:", values)

    # Створюємо ембедінги
    key_embeddings = model.encode(keys, convert_to_tensor=True)
    message_embedding = model.encode(message, convert_to_tensor=True)

    # Косинусна схожість
    cos_scores = util.cos_sim(message_embedding, key_embeddings)[0]

    # Вибираємо індекси з cos_score > similarity_threshold
    valid_scores = [(idx, float(score)) for idx, score in enumerate(cos_scores) if score > similarity_threshold]

    # Сортуємо за схожістю
    valid_scores.sort(key=lambda x: x[1], reverse=True)

    # Беремо топ-K
    top_indices = [idx for idx, _ in valid_scores[:top_k]]

    # Формуємо фінальний список ключ-значення
    results = [{"key": keys[idx], "value": values[idx]} for idx in top_indices]

    return results


def build_ai_request(user, character: Character, chat_settings: ChatSettings, worldbook_slug=None, message: str = None):
    """
    Формує JSON-запит для моделі ШІ (структурований і читабельний).
    Використовує message як останнє повідомлення користувача.
    Якщо message=None, підвантажує останнє повідомлення з файлу чату.
    """

    # 1. Завантажуємо ChatSettings JSON
    settings_data = {}
    if chat_settings and chat_settings.json_file and hasattr(chat_settings.json_file, "path"):
        try:
            with open(chat_settings.json_file.path, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
        except Exception:
            settings_data = {}

    # Витягуємо ядро (core) і системні промпти
    core_keys = {"max_tokens", "seed", "sampling"}
    core_data = {k: settings_data[k] for k in core_keys if k in settings_data}
    system_prompts = {k: v for k, v in settings_data.items() if k not in core_keys}

    # 2. Character description
    character_data = {
        "name": character.name,
        "description": character.description,
        "scenario": character.scenario,
        "initial_message": character.initial_message,
        "creator_notes": character.creator_notes,
    }

    # 3. Chat history та останнє повідомлення користувача
    chat_history = []
    last_user_message = None

    if message is not None:
        # Використовуємо передане повідомлення
        last_user_message = ("user", "now", message, "neutral")  # можна замінити "now" на datetime.now().strftime("%H:%M")
        chat_history = []  # не беремо історію з файлу, або можна передати частину історії з messages, якщо потрібно
    elif character.chat_log_file and hasattr(character.chat_log_file, "path"):
        try:
            with open(character.chat_log_file.path, "r", encoding="utf-8") as f:
                messages = json.load(f)

            user_messages = [msg for msg in messages if msg[0] == "user"]

            if user_messages:
                last_user_message = user_messages[-1]

                last_user_index = messages.index(last_user_message)
                chat_history = messages[max(0, last_user_index - 5):last_user_index]

        except Exception:
            chat_history = []
            last_user_message = None

    # 4. User persona
    user_persona = {
        "persona_name": getattr(user, "persona_name", None),
        "persona_description": getattr(user, "persona_description", None),
        "name": getattr(user, "name", user.username),
        "date_birth": user.date_birth.isoformat() if getattr(user, "date_birth", None) else None,
    }

    # 5. Worldbook matches
    worldbook_matches = []
    print("LAST_USER_MESSAGE", last_user_message)
    if last_user_message and worldbook_slug:
        try:
            worldbook_matches = get_worldbook_matches(last_user_message[2], worldbook_slug, top_k=5)
        except Exception as e:
            print(f"Worldbook match error: {e}")
            worldbook_matches = []

    # Формуємо фінальний JSON
    ai_request = {
        "Core": core_data,
        "SystemPrompts": system_prompts,
        "CharacterDescription": character_data,
        "ChatHistory": chat_history,
        "LastUserMessage": last_user_message,
        "UserPersona": user_persona,
        "AdditionalContext": worldbook_matches,
    }


    print(ai_request)
    return ai_request



import json
import numpy as np
from sentence_transformers import SentenceTransformer, util
from .models import Worldbook

# Завантажуємо модель для семантичного пошуку
model = SentenceTransformer('all-MiniLM-L6-v2')


# def get_worldbook_matches(message, worldbook_slug, top_k=5):
#     """
#     Пошук найбільш релевантних ключів у worldbook для заданого повідомлення.
#
#     :param message: рядок, що містить користувацьке повідомлення
#     :param worldbook_slug: slug обраного worldbook
#     :param top_k: кількість найбільш релевантних результатів
#     :return: список словників {key, value, similarity}
#     """
#     print("INFO====================")
#     print(message, worldbook_slug)
#
#     try:
#         wb = Worldbook.objects.get(slug=worldbook_slug)
#     except Worldbook.DoesNotExist:
#         return []
#
#     if not wb.json_file:
#         return []
#
#     # Завантаження JSON
#     wb.json_file.open('r', encoding='utf-8')
#     data = json.load(wb.json_file)
#     wb.json_file.close()
#
#     keys = list(data.keys())
#     values = list(data.values())
#
#     # Створюємо ембедінги для ключів
#     key_embeddings = model.encode(keys, convert_to_tensor=True)
#     message_embedding = model.encode(message, convert_to_tensor=True)
#
#     # Обчислюємо схожість косинусом
#     cos_scores = util.cos_sim(message_embedding, key_embeddings)[0]
#
#     # Вибираємо топ-k найбільш схожих
#     top_results = np.argpartition(-cos_scores, range(top_k))[:top_k]
#
#     results = []
#     for idx in top_results:
#         results.append({
#             "key": keys[idx],
#             "value": values[idx],
#             "similarity": float(cos_scores[idx])
#         })
#
#     # Сортуємо за схожістю
#     results = sorted(results, key=lambda x: x['similarity'], reverse=True)
#
#     return results

