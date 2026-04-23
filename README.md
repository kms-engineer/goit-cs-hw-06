# goit-cs-hw-06

Найпростіший вебзастосунок на Python без вебфреймворків. Застосунок запускає HTTP-сервер на порту `3000` і окремий socket-сервер на порту `5000`, який зберігає повідомлення у MongoDB.

## Можливості

- маршрутизація для `index.html` і `message.html`
- обробка статичних ресурсів `style.css` і `logo.png`
- повернення `error.html` для `404 Not Found`
- передача даних із форми через socket на окремий сервер
- збереження повідомлень у MongoDB у форматі:

```json
{
  "date": "2026-04-23 12:00:00.000000",
  "username": "krabaton",
  "message": "First message"
}
```

## Запуск

Запустіть середовище:

```bash
docker compose up --build
```

Після запуску застосунок буде доступний за адресою:

- [http://localhost:3000](http://localhost:3000)

## Доступні маршрути

- `/` — головна сторінка
- `/index.html` — головна сторінка
- `/message` — сторінка з формою
- `/message.html` — сторінка з формою
- будь-який неіснуючий маршрут — сторінка `404`

## Перевірка збережених повідомлень

Переглянути всі повідомлення:

```bash
docker compose exec mongodb mongosh --quiet --eval "db.getSiblingDB('messages_db').messages.find({}, {_id: 0}).pretty()"
```

Переглянути останнє повідомлення:

```bash
docker compose exec mongodb mongosh --quiet --eval "db.getSiblingDB('messages_db').messages.find({}, {_id: 0}).sort({date: -1}).limit(1).pretty()"
```

Переглянути логи застосунку:

```bash
docker compose logs app
```