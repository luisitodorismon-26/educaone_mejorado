/**
 * Lectura de la respuesta de `POST /api/calificaciones-primaria`.
 *
 * El backend responde 200 aunque haya saltado un período cerrado: guarda lo que
 * puede y avisa de lo que no. Esa política es deliberada —P1 cerrado y P2
 * abierto tienen que poder guardarse en la misma operación— pero obliga a mirar
 * el cuerpo de la respuesta: quedarse en el código de estado hace que la
 * pantalla diga "Guardado" cuando parte de lo enviado NO se guardó.
 *
 * Aquí no se decide nada sobre períodos: la autoridad sigue siendo el backend.
 * Esto solo lee lo que él ya decidió.
 */

/** El aviso de la respuesta, o null si todo entró. */
export const avisoPeriodoCerrado = (data: any): string | null => {
  const ignorados = data?.periodos_cerrados_ignorados;
  if (!Array.isArray(ignorados) || ignorados.length === 0) return null;
  return (
    data?.aviso ||
    `No se guardaron los períodos ${ignorados.map((p: number) => `P${p}`).join(', ')} porque están cerrados.`
  );
};

/** Un solo texto para toda la operación, sin repetir el mismo aviso N veces. */
export const mensajeAvisos = (avisos: string[]): string =>
  Array.from(new Set(avisos)).join(' ');
