<?php
declare(strict_types=1);
require __DIR__ . '/auth.php';
require_rewe_login();

header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

$payload = file_get_contents('php://input');
$groups = json_decode($payload, true, 512, JSON_THROW_ON_ERROR);

if (!is_array($groups)) {
    throw new RuntimeException('Expected a JSON object');
}

$encoded = json_encode($groups, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR);
if (file_put_contents(__DIR__ . '/groups.json', $encoded . "\n", LOCK_EX) === false) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Could not save groups']);
    exit;
}

echo json_encode(['ok' => true]);
