from telethon import TelegramClient, types

api_id = 35153027
api_hash = '275a7916b30391e446366433d5427086'

session_name = 'sesi_cek-group'

async def main():
    async with TelegramClient(session_name, api_id, api_hash) as client:
        print("Sedang mengambil daftar grup... Mohon tunggu.\n")
        
        dialogs = await client.get_dialogs()
        
        count = 0
        print(f"{'No':<4} | {'ID Grup':<15} | {'Nama Grup'}")
        print("-" * 50)

        for dialog in dialogs:
            if dialog.is_group:
                count += 1
                print(f"{count:<4} | {dialog.id:<15} | {dialog.name}")

        if count == 0:
            print("Tidak ditemukan grup pada akun ini.")
        else:
            print(f"\nBerhasil menemukan {count} grup.")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())