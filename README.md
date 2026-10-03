## NarrativeAI


### Usage

```shell
python -m venv myenv
source myenv/bin/activate
```

```shell
pip install -r requirements.txt
```

Optional: semantic (meaning-based) lorebook search. Large download (PyTorch);
only needed if you enable "Semantic search" in a worldbook's settings.

```shell
pip install -r requirements-semantic.txt
```

```shell
cd narrative
python manage.py migrate
```

```shell
python manage.py runserver
```
