<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;

class RunTelegramBot extends Command
{
    protected $signature = 'telegram:run';
    protected $description = 'Run Telegram bot Python script';

    public function handle()
    {
        $pythonScript = base_path('telegram_bot.py');
        exec("python {$pythonScript}");
    }
}

