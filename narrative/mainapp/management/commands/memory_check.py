"""
The cold-reader check for story memory (docs/PLAN.md, C1): a fresh model gets only a chat's story memory, the
way the chat model reads it, and answers questions about the story. A good memory lets it answer "Who is Ivan?"
or "What did she promise?" without ever seeing the chat.

    python manage.py memory_check <chat id> "Who is Ivan?" "What did Rose promise?"
    python manage.py memory_check <chat id> --file questions.txt       (one question per line)

It runs on the chat owner's "memory" model (Connections) and prints each answer; "not in memory" means the
memory is missing something it should have kept.
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Ask questions a story memory should answer, with nothing but the memory (the cold-reader check)."

    def add_arguments(self, parser):
        parser.add_argument("chat_id", type=int)
        parser.add_argument("questions", nargs="*")
        parser.add_argument("--file")

    def handle(self, chat_id, questions, file=None, **_):
        from mainapp import ai_client, chats, story_memory
        from mainapp.models import Chat
        chat = Chat.objects.filter(id=chat_id).select_related("character__author").first()
        if chat is None:
            raise CommandError("No such chat.")
        if file:
            with open(file, encoding="utf-8") as f:
                questions += [line.strip() for line in f if line.strip()]
        if not questions:
            raise CommandError("Give at least one question.")
        text = story_memory.prompt_text(chats.read(chat).get("memory"))
        if not text:
            raise CommandError("This chat has no story memory yet.")
        self.stdout.write(f"Memory: ~{len(text) // 4} tokens\n")
        user = chat.character.author
        for q in questions:
            answer = ai_client.complete(user, "memory", [
                {"role": "system", "content": "You only know the story memory below; you never saw the story. Answer "
                                              "the question from it in one or two sentences. If it doesn't say, answer "
                                              "exactly: not in memory.\n\n" + text},
                {"role": "user", "content": q}], temperature=0, max_tokens=400)
            self.stdout.write(f"\nQ: {q}\nA: {(answer or '').strip()}")
