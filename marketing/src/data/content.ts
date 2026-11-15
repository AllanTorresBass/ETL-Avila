export const WA_NUMBER = "584121716058";
export const WA_URL = `https://wa.me/${WA_NUMBER}`;

export const NAV_LINKS = [
  { to: "/", label: "Inicio" },
  { to: "/nosotros", label: "Nosotros" },
  { to: "/servicios", label: "Servicios" },
  { to: "/equipo-medico", label: "Equipo Médico" },
  { to: "/contacto", label: "Contacto" },
] as const;

export const SERVICES = [
  {
    id: "cardiology-unit",
    title: "Unidad de Cardiología avanzada",
    summary: "Diagnóstico cardiovascular, electrocardiogramas, ecocardiogramas",
    bullets: ["ECG y monitoreo", "Ecocardiograma", "Seguimiento cardiológico"],
  },
  {
    id: "radiology-imaging-unit",
    title: "Unidad de Radiología e imágenes",
    summary: "Radiología digital y ultrasonido",
    bullets: ["Radiología digital", "Ultrasonido", "Informes oportunos"],
  },
  {
    id: "occupational-medicine",
    title: "Medicina Ocupacional",
    summary: "Preempleo, control periódico, certificaciones, jornadas",
    bullets: ["Exámenes preempleo", "Control periódico", "Certificaciones"],
  },
  {
    id: "clinical-laboratory",
    title: "Laboratorio Clínico",
    summary: "Análisis clínicos con resultados confiables",
    bullets: ["Perfiles básicos", "Pruebas especializadas", "Toma a domicilio"],
  },
  {
    id: "primary-medical-assistance",
    title: "Asistencia médica primaria",
    summary: "Atención inicial y orientación clínica",
    bullets: ["Valoración inicial", "Orientación", "Referencia oportuna"],
  },
  {
    id: "covid-protocol",
    title: "Protocolo COVID",
    summary: "Evaluación y seguimiento según protocolo vigente",
    bullets: ["Evaluación", "Seguimiento", "Orientación familiar"],
  },
  {
    id: "telemedicine",
    title: "Telemedicina",
    summary: "Consultas remotas disponibles 12 h/7",
    bullets: ["Consulta por video", "Seguimiento", "Orientación 12 h/7"],
  },
  {
    id: "lab-home",
    title: "Toma de muestras en casa",
    summary: "Personal capacitado en el hogar del paciente",
    bullets: ["Agenda flexible", "Personal capacitado", "Resultados digitales"],
  },
  {
    id: "home-consultations",
    title: "Consultas en el hogar",
    summary: "Médicos en domicilio en Valera y alrededores",
    bullets: ["Médico a domicilio", "Valoración integral", "Recetas y órdenes"],
  },
  {
    id: "elective-surgeries",
    title: "Cirugías electivas",
    summary: "Coordinación quirúrgica con red aliada",
    bullets: ["Preoperatorio", "Coordinación", "Seguimiento"],
  },
] as const;

export const HOME_UNITS = SERVICES.slice(0, 3);

export const HOME_GRID = [
  "Radiología e imágenes",
  "Cardiología",
  "Enfermería",
  "Especialidades médicas",
  "Protocolo COVID",
  "Telemedicina",
  "Toma de muestras en casa",
  "Consultas en el hogar",
] as const;

export const PROOF = [
  { title: "Profesionales", subtitle: "Altamente calificados" },
  { title: "Atención rápida", subtitle: "Y personalizada" },
  { title: "Tecnología", subtitle: "De vanguardia" },
  { title: "Hogar y Sede", subtitle: "Atención integral" },
] as const;

export const PARTNERS = [
  { name: "Latitud Seguros", sector: "Aseguradora" },
  { name: "Seguros Miranda", sector: "Aseguradora" },
  { name: "Seguros Altamira", sector: "Aseguradora" },
  { name: "Seguros Venezuela", sector: "Aseguradora" },
  { name: "Mapfre", sector: "Aseguradora" },
  { name: "Banco de Venezuela (BDV)", sector: "Banca" },
  { name: "Banco Bicentenario del Pueblo", sector: "Banca" },
  { name: "Seguros La Previsora", sector: "Aseguradora" },
  { name: "Seguros Constitución", sector: "Aseguradora" },
  { name: "Cuidamed", sector: "Salud" },
  { name: "Grupo Nueve Once", sector: "Salud" },
  { name: "Redyplan", sector: "Salud" },
  { name: "Hispana de Seguros", sector: "Aseguradora" },
  { name: "Cemento Andino", sector: "Industria" },
  { name: "El Poder de la Limpieza", sector: "Servicios" },
  { name: "Makroval", sector: "Retail" },
  { name: "Valera Import", sector: "Comercio" },
  { name: "Super Max Hipermercado", sector: "Retail" },
  { name: "Inversiones y Distribuciones Mi Ángel", sector: "Comercio" },
  { name: "U.E. Colegio Privado Cristóbal de Mendoza", sector: "Educación" },
  { name: "Fi-ven", sector: "Servicios" },
  { name: "Palpitar Trujillano", sector: "Medios" },
  { name: "Haz Médica", sector: "Salud" },
  { name: "Grupo Odontológico Torres (GOT)", sector: "Salud" },
  { name: "Porcelanatos y Cerámicas Valera", sector: "Comercio" },
  { name: "Grupo Figue", sector: "Comercio" },
  { name: "Clínica Dental Cyty Dent Plus", sector: "Salud" },
  { name: "Won Motors S.A.", sector: "Automotriz" },
] as const;

export const DOCTOR_CATEGORIES = [
  "Todas",
  "Medicina General",
  "Pediatría",
  "Cardiología",
  "Traumatología",
  "Ginecología",
  "Cirugía",
  "Medicina Interna",
  "Otras Especialidades",
] as const;

/** Live directory length — not the published “45+” marketing figure. */
export const DOCTORS = [
  { id: "1", name: "Dra. María González", specialty: "Medicina General", category: "Medicina General" },
  { id: "2", name: "Dr. Luis Pérez", specialty: "Medicina General", category: "Medicina General" },
  { id: "3", name: "Dra. Ana Rojas", specialty: "Medicina General", category: "Medicina General" },
  { id: "4", name: "Dr. Carlos Méndez", specialty: "Medicina General", category: "Medicina General" },
  { id: "5", name: "Dra. Paula Díaz", specialty: "Medicina General", category: "Medicina General" },
  { id: "6", name: "Dra. Sofía Vargas", specialty: "Pediatría", category: "Pediatría" },
  { id: "7", name: "Dr. Andrés Lima", specialty: "Pediatría", category: "Pediatría" },
  { id: "8", name: "Dra. Carmen Silva", specialty: "Pediatría", category: "Pediatría" },
  { id: "9", name: "Dr. José Rivas", specialty: "Pediatría", category: "Pediatría" },
  { id: "10", name: "Dra. Elena Torres", specialty: "Pediatría", category: "Pediatría" },
  { id: "11", name: "Dr. Miguel Castro", specialty: "Pediatría", category: "Pediatría" },
  { id: "12", name: "Dra. Laura Núñez", specialty: "Pediatría", category: "Pediatría" },
  { id: "13", name: "Dr. Roberto Herrera", specialty: "Cardiología", category: "Cardiología" },
  { id: "14", name: "Dra. Isabel Moreno", specialty: "Cardiología", category: "Cardiología" },
  { id: "15", name: "Dr. Fernando Ortiz", specialty: "Cardiología", category: "Cardiología" },
  { id: "16", name: "Dr. Hugo Ramírez", specialty: "Traumatología", category: "Traumatología" },
  { id: "17", name: "Dra. Patricia León", specialty: "Ginecología", category: "Ginecología" },
  { id: "18", name: "Dra. Valentina Cruz", specialty: "Ginecología", category: "Ginecología" },
  { id: "19", name: "Dra. Gabriela Soto", specialty: "Ginecología", category: "Ginecología" },
  { id: "20", name: "Dra. Daniela Paredes", specialty: "Ginecología", category: "Ginecología" },
  { id: "21", name: "Dra. Natalia Vega", specialty: "Ginecología", category: "Ginecología" },
  { id: "22", name: "Dra. Andrea Molina", specialty: "Ginecología", category: "Ginecología" },
  { id: "23", name: "Dr. Ricardo Álvarez", specialty: "Cirugía General", category: "Cirugía" },
  { id: "24", name: "Dr. Esteban Quintero", specialty: "Cirugía General", category: "Cirugía" },
  { id: "25", name: "Dra. Mónica Salas", specialty: "Cirugía General", category: "Cirugía" },
  { id: "26", name: "Dr. Javier Blanco", specialty: "Medicina Interna", category: "Medicina Interna" },
  { id: "27", name: "Dra. Claudia Reyes", specialty: "Medicina Interna", category: "Medicina Interna" },
  { id: "28", name: "Dr. Pedro Aguilar", specialty: "Dermatología", category: "Otras Especialidades" },
  { id: "29", name: "Dra. Lucía Campos", specialty: "Oftalmología", category: "Otras Especialidades" },
  { id: "30", name: "Dr. Sergio Duarte", specialty: "Otorrinolaringología", category: "Otras Especialidades" },
  { id: "31", name: "Dra. Rosa Jiménez", specialty: "Neurología", category: "Otras Especialidades" },
  { id: "32", name: "Dr. Manuel Ponce", specialty: "Urología", category: "Otras Especialidades" },
  { id: "33", name: "Dra. Beatriz Flores", specialty: "Endocrinología", category: "Otras Especialidades" },
  { id: "34", name: "Dr. Álvaro Medina", specialty: "Gastroenterología", category: "Otras Especialidades" },
  { id: "35", name: "Dra. Irene Castillo", specialty: "Neumología", category: "Otras Especialidades" },
  { id: "36", name: "Dr. Diego Navarro", specialty: "Psiquiatría", category: "Otras Especialidades" },
  { id: "37", name: "Dra. Camila Ortiz", specialty: "Psicología Clínica", category: "Otras Especialidades" },
  { id: "38", name: "Dr. Tomás Espinoza", specialty: "Fisiatría", category: "Otras Especialidades" },
  { id: "39", name: "Dra. Adriana Peña", specialty: "Nutrición", category: "Otras Especialidades" },
  { id: "40", name: "Dr. Felipe Guerra", specialty: "Anestesiología", category: "Otras Especialidades" },
  { id: "41", name: "Dra. Verónica Sandoval", specialty: "Radiología", category: "Otras Especialidades" },
  { id: "42", name: "Dr. Ignacio Valdez", specialty: "Laboratorio Clínico", category: "Otras Especialidades" },
  { id: "43", name: "Dra. Mariana Contreras", specialty: "Medicina Familiar", category: "Otras Especialidades" },
  { id: "44", name: "Dr. Óscar Delgado", specialty: "Geriatría", category: "Otras Especialidades" },
  { id: "45", name: "Dra. Juliana Acosta", specialty: "Reumatología", category: "Otras Especialidades" },
  { id: "46", name: "Dr. Nicolás Bravo", specialty: "Infectología", category: "Otras Especialidades" },
  { id: "47", name: "Dra. Helena Fuentes", specialty: "Alergología", category: "Otras Especialidades" },
  { id: "48", name: "Dr. Rafael Mendoza", specialty: "Medicina del Deporte", category: "Otras Especialidades" },
] as const;

export const PUBLISHED_STATS = [
  { value: "15+", label: "Años de Experiencia", description: "Líderes en gestión médica profesional" },
  { value: "12 h/7", label: "Atención Continua", description: "Telemedicina y orientación disponible" },
  { value: "45+", label: "Especialistas Médicos", description: "Cuerpo profesional capacitado (figura publicada)" },
  { value: "28+", label: "Empresas Aliadas", description: "Confían en nuestra cobertura" },
] as const;

export const ALLIED_CLINICS = [
  { name: "Clínica UGA", city: "Valera", tag: "Centro Hospitalario" },
  { name: "Centro Clínico de Cirugía JGH", city: "Valera", tag: "Cirugía Especializada" },
  { name: "Centro Médico Las Acacias", city: "Valera", tag: "Atención Integral" },
  { name: "Centro Médico Quirúrgico Carvajal C.A.", city: "Valera", tag: "Cirugía" },
  { name: "Laboratorio de Microbiología Rosa Mística", city: "Valera", tag: "Laboratorio" },
  { name: "Rehabilser", city: "Valera", tag: "Rehabilitación" },
  { name: "Laboratorio Clínico Ramar", city: "Valera", tag: "Laboratorio" },
  { name: "Óptica en Línea", city: "Valera", tag: "Salud Visual" },
  { name: "Grupo Odontológico Torres (GOT)", city: "Valera", tag: "Odontología Especializada" },
  { name: "Centro Ocular Corredor", city: "Valera", tag: "Oftalmología Avanzada" },
  { name: "Anhelab C.A. Laboratorio Clínico", city: "Valera", tag: "Pruebas Especiales" },
] as const;

export const APPOINTMENT_SERVICES = [
  "Consultas con especialistas",
  "Cirugías electivas",
  "Servicios de Radiología",
  "Servicios de Imágenes",
  "Servicio de Enfermería",
  "Medicina Ocupacional",
  "Servicios de laboratorio",
  "Consultas en el hogar",
  "Telemedicina",
  "Protocolo COVID",
] as const;

export const CONTACT_REQUIREMENTS = [
  "Consulta Médica en Casa",
  "Telemedicina 12 h/7",
  "Laboratorio a Domicilio",
  "Cirugías Electivas",
  "Afiliación Empresarial",
  "Otro Asunto",
] as const;

export const CONTACT_INFO = {
  address: "Av. Bolívar entre calles 18 y 19, C.C. Las Acacias, Local 10-A, Valera, estado Trujillo.",
  hours: "Lunes a viernes de 7:00 am a 5:00 pm",
  phones: "0412-1716058 / 0271-2310949",
  email: "gpsavila2@gmail.com",
  instagram: "@gpsavila.ve",
} as const;

export const HERO_CHIPS = [
  "Asistencia médica primaria",
  "Telemedicina 12 h/7",
  "Médicos en el hogar",
  "Cirugías electivas",
] as const;
