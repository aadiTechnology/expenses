// Minimal translation layer. English is the source text; Hindi and Marathi cover navigation and page titles only.
// Translations are a first draft and need review by a native speaker before release.
export type Lang = 'en' | 'hi' | 'mr'
export const LANGS: { code: Lang; label: string }[] = [{ code: 'en', label: 'English' }, { code: 'hi', label: 'हिन्दी' }, { code: 'mr', label: 'मराठी' }]

const D: Record<Exclude<Lang, 'en'>, Record<string, string>> = {
  hi: {
    Dashboard: 'डैशबोर्ड', Transactions: 'लेन-देन', 'Add Expense': 'खर्च जोड़ें', Income: 'आय', Accounts: 'खाते', Categories: 'श्रेणियाँ', Budgets: 'बजट',
    Family: 'परिवार', Goals: 'लक्ष्य', 'AI Assistant': 'एआई सहायक', Reports: 'रिपोर्ट', Settings: 'सेटिंग्स', 'My Expenses': 'मेरे खर्च', Approvals: 'स्वीकृतियाँ',
    Reimbursements: 'प्रतिपूर्ति', Departments: 'विभाग', Projects: 'परियोजनाएँ', 'Growth Spend': 'विकास व्यय', 'Organization Settings': 'संगठन सेटिंग्स',
    'Sign out': 'साइन आउट', 'My expenses': 'मेरे खर्च', 'Savings goals': 'बचत लक्ष्य', 'Organization settings': 'संगठन सेटिंग्स', Language: 'भाषा',
  },
  mr: {
    Dashboard: 'डॅशबोर्ड', Transactions: 'व्यवहार', 'Add Expense': 'खर्च जोडा', Income: 'उत्पन्न', Accounts: 'खाती', Categories: 'वर्ग', Budgets: 'अंदाजपत्रक',
    Family: 'कुटुंब', Goals: 'उद्दिष्टे', 'AI Assistant': 'एआय सहायक', Reports: 'अहवाल', Settings: 'सेटिंग्ज', 'My Expenses': 'माझे खर्च', Approvals: 'मंजुरी',
    Reimbursements: 'परतफेड', Departments: 'विभाग', Projects: 'प्रकल्प', 'Growth Spend': 'वाढ खर्च', 'Organization Settings': 'संस्था सेटिंग्ज',
    'Sign out': 'साइन आउट', 'My expenses': 'माझे खर्च', 'Savings goals': 'बचत उद्दिष्टे', 'Organization settings': 'संस्था सेटिंग्ज', Language: 'भाषा',
  },
}
export const translate = (lang: Lang, text: string) => (lang === 'en' ? text : D[lang][text] ?? text)
export const getLang = (): Lang => { try { return (localStorage.getItem('spendos.lang') as Lang) || 'en' } catch { return 'en' } }
export const saveLang = (l: Lang) => { try { localStorage.setItem('spendos.lang', l) } catch { /* private mode */ } }
