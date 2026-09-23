<?php
declare(strict_types=1);

require __DIR__ . '/auth.php';
require_rewe_login();

$filename = basename((string) ($_GET['file'] ?? ''));
$pdfDirectory = __DIR__ . '/pdfs';
$path = realpath($pdfDirectory . '/' . $filename);
$directory = realpath($pdfDirectory);

if ($filename === ''
    || strtolower(pathinfo($filename, PATHINFO_EXTENSION)) !== 'pdf'
    || $path === false
    || $directory === false
    || !str_starts_with($path, $directory . DIRECTORY_SEPARATOR)
    || !is_file($path)) {
    http_response_code(404);
    exit('PDF nicht gefunden.');
}

header('Content-Type: application/pdf');
header("Content-Disposition: inline; filename*=UTF-8''" . rawurlencode($filename));
header('Content-Length: ' . (string) filesize($path));
header('Cache-Control: private, max-age=300');
header('X-Content-Type-Options: nosniff');
readfile($path);
