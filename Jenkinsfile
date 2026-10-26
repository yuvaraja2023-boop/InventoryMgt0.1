// ==============================================================================
// Jenkinsfile - Smart Inventory Management System
// Continuous Integration Pipeline for College SCM Project
// Cross-platform support (Linux / Windows Jenkins build agents)
// ==============================================================================

pipeline {
    agent any

    options {
        timeout(time: 15, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
    }

    environment {
        PYTHONUNBUFFERED = '1'
        TEST_REPORTS_DIR = 'test-reports'
    }

    stages {
        stage('Checkout SCM') {
            steps {
                echo 'Checking out source repository branch...'
                checkout scm
            }
        }

        stage('Prepare Environment') {
            steps {
                echo 'Setting up Python virtual environment and dependencies directory...'
                script {
                    if (isUnix()) {
                        sh '''
                            python3 -m venv .venv || virtualenv .venv
                            . .venv/bin/activate
                            python -m pip install --upgrade pip
                        '''
                    } else {
                        bat '''
                            python -m venv .venv
                            call .venv\\Scripts\\activate.bat
                            python -m pip install --upgrade pip
                        '''
                    }
                }
            }
        }

        stage('Install Dependencies') {
            steps {
                echo 'Installing required packages from requirements.txt...'
                script {
                    if (isUnix()) {
                        sh '''
                            . .venv/bin/activate
                            pip install -r requirements.txt
                        '''
                    } else {
                        bat '''
                            call .venv\\Scripts\\activate.bat
                            pip install -r requirements.txt
                        '''
                    }
                }
            }
        }

        stage('Code Syntax Verification') {
            steps {
                echo 'Verifying Python source syntax compilation...'
                script {
                    if (isUnix()) {
                        sh '''
                            . .venv/bin/activate
                            python -m compileall -q app.py database.py tests/
                        '''
                    } else {
                        bat '''
                            call .venv\\Scripts\\activate.bat
                            python -m compileall -q app.py database.py tests/
                        '''
                    }
                }
            }
        }

        stage('Run Automated Pytest Suite') {
            steps {
                echo 'Executing Pytest automated test suite and generating JUnit XML report...'
                script {
                    if (isUnix()) {
                        sh '''
                            mkdir -p ${TEST_REPORTS_DIR}
                            . .venv/bin/activate
                            pytest --junitxml=${TEST_REPORTS_DIR}/junit-results.xml
                        '''
                    } else {
                        bat '''
                            if not exist %TEST_REPORTS_DIR% mkdir %TEST_REPORTS_DIR%
                            call .venv\\Scripts\\activate.bat
                            pytest --junitxml=%TEST_REPORTS_DIR%\\junit-results.xml
                        '''
                    }
                }
            }
        }

        stage('Publish Test Results') {
            steps {
                echo 'Publishing JUnit test results to Jenkins dashboard...'
                junit allowEmptyResults: true, testResults: "${TEST_REPORTS_DIR}/*.xml"
            }
        }
    }

    post {
        always {
            echo 'Pipeline execution finished.'
            cleanWs deleteDirs: true, notFailBuild: true, patterns: [
                [pattern: '.pytest_cache/**', type: 'INCLUDE'],
                [pattern: '__pycache__/**', type: 'INCLUDE']
            ]
        }
        success {
            echo 'SUCCESS: All automated unit and integration tests passed! SCM build verified.'
        }
        failure {
            echo 'FAILURE: One or more tests failed. Check test-reports/junit-results.xml for failure traces.'
        }
    }
}
