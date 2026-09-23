<?php
declare(strict_types=1);
require __DIR__ . '/auth.php';
start_rewe_session();
$_SESSION = [];
session_destroy();
header('Location: /login.php', true, 303);
exit;
