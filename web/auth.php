<?php
declare(strict_types=1);

function start_rewe_session(): void
{
    if (session_status() !== PHP_SESSION_ACTIVE) {
        session_set_cookie_params([
            'lifetime' => 60 * 60 * 24 * 30,
            'path' => '/',
            'secure' => true,
            'httponly' => true,
            'samesite' => 'Lax',
        ]);
        session_start();
    }
}

function valid_rewe_credentials(string $username, string $password): bool
{
    $line = trim((string) file_get_contents(__DIR__ . '/.htpasswd'));
    [$storedUsername, $hash] = array_pad(explode(':', $line, 2), 2, '');

    return $storedUsername !== ''
        && hash_equals($storedUsername, $username)
        && password_verify($password, $hash);
}

function require_rewe_login(): void
{
    start_rewe_session();
    if (empty($_SESSION['rewe_authenticated'])) {
        header('Location: /login.php', true, 303);
        exit;
    }
}
