<?php
declare(strict_types=1);
require __DIR__ . '/auth.php';
start_rewe_session();

if (!empty($_SESSION['rewe_authenticated'])) {
    header('Location: /dashboard.php', true, 303);
    exit;
}

$error = false;
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $username = (string) ($_POST['username'] ?? '');
    $password = (string) ($_POST['password'] ?? '');
    if (valid_rewe_credentials($username, $password)) {
        session_regenerate_id(true);
        $_SESSION['rewe_authenticated'] = true;
        header('Location: /dashboard.php', true, 303);
        exit;
    }
    $error = true;
}
?>
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#cc0000">
  <title>REWE-Auswertung anmelden</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100svh; display: grid; place-items: center; padding: 24px; background: radial-gradient(circle at top, #fff7f7, #f3f4f6 58%, #e8eaed); color: #1f2937; }
    main { width: min(100%, 410px); background: rgba(255,255,255,.94); border: 1px solid #e5e7eb; border-radius: 24px; padding: 32px; box-shadow: 0 20px 50px rgba(31,41,55,.16); }
    .mark { width: 52px; height: 52px; display: grid; place-items: center; border-radius: 16px; background: #cc0000; color: white; font-size: 24px; margin-bottom: 24px; }
    h1 { font-size: 1.5rem; margin: 0 0 8px; letter-spacing: -.02em; }
    p { color: #6b7280; line-height: 1.5; margin: 0 0 28px; }
    label { display: block; font-size: .9rem; font-weight: 650; margin: 16px 0 7px; }
    input { width: 100%; border: 1px solid #d1d5db; border-radius: 12px; padding: 13px 14px; font: inherit; background: #fff; }
    input:focus { outline: 3px solid rgba(204,0,0,.18); border-color: #cc0000; }
    button { width: 100%; margin-top: 24px; border: 0; border-radius: 12px; padding: 14px; background: #cc0000; color: white; font: 700 1rem inherit; cursor: pointer; }
    button:hover { background: #ad0000; }
    .error { margin: 0 0 18px; padding: 12px; border-radius: 10px; background: #fff1f2; color: #b42318; font-size: .9rem; }
    .note { margin-top: 20px; font-size: .78rem; text-align: center; color: #9ca3af; }
  </style>
</head>
<body>
  <main>
    <div class="mark" aria-hidden="true">R</div>
    <h1>REWE-Auswertung</h1>
    <p>Bitte melde dich an, um deine persönliche Einkaufsanalyse zu öffnen.</p>
    <?php if ($error): ?><div class="error" role="alert">Benutzername oder Passwort stimmt nicht.</div><?php endif; ?>
    <form method="post" action="/login.php">
      <label for="username">Benutzername</label>
      <input id="username" name="username" autocomplete="username" required autofocus>
      <label for="password">Passwort</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Anmelden</button>
    </form>
    <div class="note">Die Verbindung ist verschlüsselt.</div>
  </main>
</body>
</html>
