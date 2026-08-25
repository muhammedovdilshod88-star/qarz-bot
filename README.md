# 📒 Qarz Daftari Telegram Boti (SaaS Multi-Store)

Ushbu bot mahalliy oziq-ovqat va boshqa do'konlar uchun qarz (nasiya) daftarini avtomatlashtirish, qarz va to'lovlarni hisoblab borish va mijozlarga Telegram orqali real vaqtda hisobot yetkazish uchun yaratilgan.

---

## 🚀 Asosiy Imkoniyatlar

### 👑 1. Super Admin (Dasturchi / Sotuvchi — Siz):
- **Do'konlarni boshqarish:** Yangi do'kon va do'konchi ochib berish (faqat Telegram ID sini kiritish yetarli).
- **Litsenziya / Bloklash:** Do'konni vaqtincha bloklash yoki qayta faollashtirish.
- **Platforma statistikasi:** Jami do'konlar, mijozlar va tizimdagi umumiy nasiyalar statistikasi.

### 🏪 2. Do'konchi (Admin) Paneli:
- **Do'kon nomi:** O'z do'koni nomini xohlagancha o'zgartirish.
- **Do'kon QR Kodi:** Bot orqali maxsus do'kon QR kodini rasm holatida yuklab olish (buni chop qilib do'konga osib qo'yadi).
- **Mijozlar ro'yxati (Filtr):** Barcha mijozlar **eng ko'p qarz olganlar bo'yicha tartiblangan** (eng katta qarz egalari yuqorida turadi).
- **Mijoz qo'shish:**
  - *Avtomatik:* Mijoz do'kondagi QR kodni skaner qilganda avtomatik ulanadi.
  - *Qo'lda:* Do'konchi ism va telefon raqamini kiritib mijoz ochishi mumkin.
- **Qarz yozish:** Summa va izoh (masalan: `yog', un, shakar`) kiritiladi.
- **To'lov ayirish:** Mijoz pul berganida summani kiritadi va qarz avtomatik kamayadi.
- **Qarz tarixi:** Har bir mijozning har bir xaridi va to'lovlari sanasi bilan to'liq saqlanadi.
- **Telegram orqali bildirishnoma:** Har safar qarz yozilganda yoki to'lov qilinganda mijozga darhol xabar boradi!

### 👤 3. Mijoz (Xaridor) Paneli:
- Do'kon QR kodini skaner qilib kiradi.
- **Mening qarzlarim:** Qaysi do'konda qancha qarzi borligini real vaqtda ko'radi.
- **Xaridlar tarixi:** Qachon qanday narsalar olganini ko'radi.

---

## 🖥 70,000 so'mlik bitta serverda 4-5 ta botni ishga tushirish (Tejamkor usul)

Aiogram 3 asinxron va SQLite juda yengil bo'lgani sababli, 1 GB RAM va 1 vCPU bo'lgan eng arzon VPS serverda (masalan, Hetzner / Timeweb / DigitalOcean / Vultr) 10-15 tagacha bunday botlarni bemalol bir vaqtda ishlatish mumkin.

### Serverda ishga tushirish (Ubuntu/Debian):
1. **Python va venv o'rnatish:**
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv git
   ```

2. **Loyiha papkasiga kirish va venv yaratish:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Har bir botni alohida fonda (Systemd xizmati sifatida) ishlatish:**
   Har bir yangi botingiz uchun `/etc/systemd/system/qarz_bot1.service` fayl yaratasiz:
   ```ini
   [Unit]
   Description=Qarz Daftari Bot 1
   After=network.target

   [Service]
   User=root
   WorkingDirectory=/root/bots/qarz_bot1
   ExecStart=/root/bots/qarz_bot1/venv/bin/python main.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   So'ngra yoqish:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now qarz_bot1
   ```
   Bunday service lardan bitta serverda 5 ta (`qarz_bot1`, `qarz_bot2`, `qarz_bot3` ...) qilib qo'ysangiz, server 24/7 o'chmasdan, xotirani deyarli band qilmay ishlayveradi.

---

## ⚙️ Ishga tushirish (Windows / Kompyuterda):

1. `config.py` yoki `.env` da kerakli parametrlarni sozlang.
2. `python main.py` ni ishga tushiring.
