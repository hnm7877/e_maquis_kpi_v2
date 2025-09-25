# 🔮 Prédictions Prophet - Frontend Next.js

## 🚀 Nouvelle Page de Prédictions IA

Une page complète intégrée dans votre frontend Next.js existant pour exploiter toute la puissance des prédictions Prophet basées sur les données de vente des produits.

## 📁 Structure Ajoutée

```
frontend/emaquis_kpi/
├── app/
│   └── predictions/
│       └── page.tsx          # Page principale des prédictions
├── components/ui/
│   ├── card.tsx              # Composants UI
│   ├── button.tsx
│   ├── select.tsx
│   ├── input.tsx
│   ├── label.tsx
│   ├── badge.tsx
│   ├── tabs.tsx
│   └── alert.tsx
├── types/
│   └── plotly.d.ts           # Types TypeScript pour Plotly
└── package.json              # Dépendances mises à jour
```

## 🎯 Fonctionnalités Implémentées

### 1. **Prédictions Prophet Avancées**
- **Modèles Prophet** avec saisonnalité annuelle, hebdomadaire et quotidienne
- **Intervalles de confiance** pour quantifier l'incertitude
- **Régresseurs externes** (montants, prix) pour améliorer la précision
- **Paramètres optimisés** pour de meilleures prédictions

### 2. **Interface Utilisateur Moderne**
- **Design responsive** avec Tailwind CSS
- **Graphiques interactifs** avec Plotly.js
- **Contrôles intuitifs** pour configurer les prédictions
- **Métriques en temps réel** avec badges colorés

### 3. **Types de Prédictions**
- **Prédictions générales** : Tous les tenants
- **Prédictions par tenant** : Analyse spécifique
- **Prédictions par produit** : Focus sur les ventes de produits
- **Comparaison multi-tenants** : Analyse comparative

### 4. **Métriques de Performance**
- **MAE** (Erreur Absolue Moyenne)
- **RMSE** (Racine de l'Erreur Quadratique Moyenne)
- **R²** (Coefficient de Détermination)
- **MAPE** (Erreur Absolue Moyenne en Pourcentage)
- **Score de Précision** personnalisé

## 🛠️ Installation et Configuration

### 1. **Installer les Dépendances**
```bash
cd frontend/emaquis_kpi
npm install plotly.js react-plotly.js
# ou
pnpm add plotly.js react-plotly.js
```

### 2. **Démarrer le Backend**
```bash
# Dans le répertoire racine
python main.py
```

### 3. **Démarrer le Frontend**
```bash
cd frontend/emaquis_kpi
npm run dev
# ou
pnpm dev
```

### 4. **Accéder à la Page**
```
http://localhost:3000/predictions
```

## 🎨 Interface Utilisateur

### **Contrôles Principaux**
- **Sélection de Tenant** : Dropdown avec tous les tenants disponibles
- **Sélection de Produit** : Dropdown avec les produits globaux
- **Jours de Prédiction** : Input numérique (7-365 jours)
- **Boutons d'Action** : Prédictions, Prédictions Produit, Métriques Précision

### **Onglets de Résultats**
1. **Prédictions** : Graphiques principaux avec intervalles de confiance
2. **Précision** : Évaluation du modèle avec données train/test
3. **Métriques** : Explication des métriques de performance

### **Graphiques Interactifs**
- **Graphique Principal** : Données historiques + Prédictions + Intervalles de confiance
- **Composantes** : Décomposition en tendance et saisonnalités
- **Comparaison** : Données réelles vs Prédictions (évaluation)

## 🔧 API Endpoints Utilisés

### **Prédictions**
```
GET /prophet/predictions?days_ahead=30&tenant_id=optional
GET /prophet/tenant/{tenant_id}?days_ahead=30
GET /prophet/products?product_name=optional&days_ahead=30
```

### **Métriques de Précision**
```
GET /prophet/accuracy-metrics?tenant_id=optional
GET /prophet/compare-tenants?days_ahead=30
```

### **Données de Base**
```
GET /analytics/sales          # Liste des tenants
GET /products/globals         # Liste des produits
```

## 📊 Types de Graphiques Plotly

### **Graphiques Principaux**
- **Scatter avec lignes** : Prédictions temporelles
- **Aires remplies** : Intervalles de confiance
- **Lignes multiples** : Comparaison de tenants
- **Graphiques en barres** : Métriques de performance

### **Fonctionnalités Interactives**
- **Zoom et pan** sur tous les graphiques
- **Tooltips personnalisés** avec informations détaillées
- **Légendes interactives** pour masquer/afficher des séries
- **Export** en PNG, PDF, SVG

## 🎯 Cas d'Usage

### **1. Prédictions Générales**
- Analyser les tendances globales des ventes
- Identifier les patterns saisonniers
- Planifier les ressources sur 30-90 jours

### **2. Prédictions par Tenant**
- Analyser les performances individuelles
- Comparer les tenants entre eux
- Optimiser les stratégies par tenant

### **3. Prédictions par Produit**
- Analyser la demande pour des produits spécifiques
- Planifier les stocks et approvisionnements
- Identifier les produits en croissance/déclin

### **4. Évaluation des Modèles**
- Valider la précision des prédictions
- Ajuster les paramètres des modèles
- Comparer les performances entre périodes

## 🔍 Fonctionnalités Avancées

### **Intelligence Artificielle**
- **Modèles Prophet** optimisés avec paramètres avancés
- **Saisonnalité automatique** (annuelle, hebdomadaire, quotidienne)
- **Gestion des changements de tendance** avec changepoints
- **Régresseurs externes** pour améliorer la précision

### **Visualisations Interactives**
- **Graphiques responsives** qui s'adaptent à tous les écrans
- **Animations fluides** pour les transitions
- **Couleurs cohérentes** avec votre design system
- **Performance optimisée** même avec de gros volumes de données

### **Expérience Utilisateur**
- **Interface intuitive** avec contrôles clairs
- **Feedback visuel** pour les actions en cours
- **Gestion d'erreurs** avec messages explicites
- **Navigation fluide** entre les différents types d'analyses

## 🚀 Prochaines Améliorations

- [ ] **Prédictions en temps réel** avec WebSockets
- [ ] **Alertes automatiques** basées sur les prédictions
- [ ] **Export des prédictions** en Excel/CSV
- [ ] **Comparaison de modèles** (Prophet vs autres)
- [ ] **Prédictions multi-variées** avec plusieurs variables
- [ ] **Dashboard personnalisable** par utilisateur

## 📞 Support

Pour toute question sur les prédictions Prophet :
- **Documentation Prophet** : https://facebook.github.io/prophet/
- **Documentation Plotly** : https://plotly.com/javascript/
- **Documentation Next.js** : https://nextjs.org/docs

## 🎉 Résultat

Vous disposez maintenant d'une page complète de prédictions IA intégrée dans votre frontend Next.js, exploitant toute la puissance de Prophet pour analyser et prédire les ventes de vos produits avec une précision maximale ! 🔮✨
